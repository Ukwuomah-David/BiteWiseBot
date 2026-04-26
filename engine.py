from datetime import datetime
import random
from sheets import get_menu_items, get_vendor_scores, get_user_vendor_scores
from core import safe_get_user, parse_list
from db import query as safe_query
import time

# =========================
# CACHE SYSTEM
# =========================
MEAL_CACHE = {}
CACHE_TTL = 15  # seconds

VENDOR_RANK_CACHE = {
    "data": {},
    "last_updated": 0
}

RANK_TTL = 300  # 5 minutes

def get_cache_key(user_id):
    user = safe_get_user(user_id)

    meals = str(parse_list(user.get("meals")))
    budget = str(user.get("budget"))
    allergies = str(parse_list(user.get("allergies")))

    return f"meal:{user_id}:{meals}:{budget}:{allergies}"


def get_cached_meal(user_id):
    key = get_cache_key(user_id)

    if key not in MEAL_CACHE:
        return None

    data, timestamp = MEAL_CACHE[key]

    if time.time() - timestamp > CACHE_TTL:
        del MEAL_CACHE[key]
        return None

    return data


def set_cached_meal(user_id, value):
    key = get_cache_key(user_id)
    MEAL_CACHE[key] = (value, time.time())

def compute_vendor_ranks():
    rows = get_vendor_scores()

    VENDOR_RANK_CACHE["data"] = rows
    VENDOR_RANK_CACHE["last_updated"] = time.time()

    return rows
    
def get_cached_vendor_scores():
    if (
        time.time() - VENDOR_RANK_CACHE["last_updated"]
        > RANK_TTL
        or not VENDOR_RANK_CACHE["data"]
    ):
        compute_vendor_ranks()

    return VENDOR_RANK_CACHE["data"]
# =========================
# SUBSCRIPTION
# =========================
def subscription_middleware(user_id):
    user = safe_get_user(user_id)
    if not user:
        return False

    expiry = user.get("subscription_expires_at")
    if not expiry:
        return False

    expiry_date = datetime.fromisoformat(str(expiry))

    if datetime.utcnow() > expiry_date:
        safe_query(
            "UPDATE users SET plan='free' WHERE telegram_id=%s",
            (str(user_id),)
        )
        return False

    return True

def save_meal_memory(user_id, meal, recs):
    if not recs:
        return

    item_penalty, _ = get_recent_memory(user_id)

    for r in recs:
        if item_penalty.get(r["item_name"], 0) > 2:
            continue

        safe_query(
            """
            INSERT INTO user_meal_memory
            (telegram_id, meal_type, item_name, vendor_name, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (
                str(user_id),
                meal,
                r.get("item_name"),
                r.get("vendor_name")
            )
        )
    
def get_recent_memory(user_id, limit=30):
    rows = safe_query(
        """
        SELECT item_name, vendor_name, created_at
        FROM user_meal_memory
        WHERE telegram_id=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(user_id), limit),
        fetch=True
    )

    item_penalty = {}
    vendor_penalty = {}

    for item_name, vendor_name, created_at in rows:
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        weight = time_decay_weight(created_at)

        item_penalty[item_name] = item_penalty.get(item_name, 0) + weight
        vendor_penalty[vendor_name] = vendor_penalty.get(vendor_name, 0) + weight

    return item_penalty, vendor_penalty
def save_feedback(user_id, item_name, vendor_name, value):
    safe_query(
        """
        INSERT INTO user_item_feedback
        (telegram_id, item_name, vendor_name, feedback)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (telegram_id, item_name)
        DO UPDATE SET feedback = EXCLUDED.feedback
        """,
        (str(user_id), item_name, vendor_name, value)
    )

def get_feedback(user_id):
    rows = safe_query(
        """
        SELECT item_name, vendor_name, feedback
        FROM user_item_feedback
        WHERE telegram_id=%s
        """,
        (str(user_id),),
        fetch=True
    )

    item_scores = {}
    vendor_scores = {}

    for item, vendor, fb in rows:
        item_scores[item] = fb
        vendor_scores[vendor] = vendor_scores.get(vendor, 0) + fb

    return item_scores, vendor_scores
# =========================
# SMART ENGINE
# =========================
def smart_recommend(user_id, meal, context=None):
    user = safe_get_user(user_id)
    if not user:
        return []

    items = get_menu_items() or []

    total_budget = int(user.get("budget", 1500))
    meals = parse_list(user.get("meals"))
    meal_count = len(meals) if meals else 2

    per_meal_budget = total_budget // meal_count
    allergies = parse_list(user.get("allergies") or "")

    # =========================
    # FILTER (budget + allergies)
    # =========================
    filtered = [
        i for i in items
        if i["price"] <= per_meal_budget
        and not any(a in i["item_name"].lower() for a in allergies)
    ]

    if not filtered:
        filtered = items

    # =========================
    # MEMORY (V2)
    # =========================
    item_penalty, vendor_penalty = get_recent_memory(user_id)
    item_feedback, vendor_feedback = get_feedback(user_id)
    def penalty_score(item):
        item_p = item_penalty.get(item["item_name"], 0)
        vendor_p = vendor_penalty.get(item["vendor_name"], 0)
        return item_p * 50 + vendor_p * 30

    # =========================
    # FREE PLAN → RANDOM
    # =========================
    if not subscription_middleware(user_id):
        if not filtered:
            return []

        return random.sample(filtered, min(3, len(filtered)))

    # =========================
    # SCORING
    # =========================
    global_scores = get_cached_vendor_scores() or {}
    user_scores = get_user_vendor_scores(user_id) or {}

    def score(item):
        price = item["price"]
        vendor = item["vendor_name"]

        price_score = per_meal_budget - price
        global_rating = global_scores.get(vendor, 3)
        user_rating = user_scores.get(vendor, 0)

        penalty = penalty_score(item)
        item_fb = item_feedback.get(item["item_name"], 0)
        vendor_fb = vendor_feedback.get(vendor, 0)
        return (
            price_score
            + (float(global_rating) * 10)
            + (float(user_rating) * 20)
            + (item_fb * 40)        # strong influence
            + (vendor_fb * 15)
            - penalty
        )

    ranked = sorted(filtered, key=score, reverse=True)

    return ranked[:5]
    
def time_decay_weight(created_at):
    """
    Newer meals = stronger penalty
    Older meals = fade out
    """
    age_seconds = (datetime.utcnow() - created_at).total_seconds()

    # decay over ~3 days
    return max(0.1, 1 - (age_seconds / (60 * 60 * 24 * 3)))
def generate_meal_payload(user_id, meal, context=None):
    """
    Returns structured meal data instead of raw text.
    This replaces build_meal_text completely.
    """

    recs = smart_recommend(user_id, meal, context)

    save_meal_memory(user_id, meal, recs)

    item_fb, vendor_fb = get_feedback(user_id)

    blocks = []
    buttons = []

    for r in recs:
        item = r["item_name"]
        vendor = r["vendor_name"]

        blocks.append(f"• {item} ({vendor}) - ₦{r['price']}")

        buttons.append([
            {
                "text": f"👍 {item[:10]}",
                "callback": f"LIKE:{vendor}|{item}"
            },
            {
                "text": f"👎 {item[:10]}",
                "callback": f"DISLIKE:{vendor}|{item}"
            }
        ])

    return {
        "meal": meal,
        "text": "🍱 " + meal.upper() + "\n\n" + "\n".join(blocks),
        "buttons": buttons
    }