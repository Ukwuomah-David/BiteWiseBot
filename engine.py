from datetime import datetime
import random
from sheets import get_menu_items, get_vendor_scores, get_user_vendor_scores
from user_service import safe_get_user, parse_list
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
    return f"meal:{user_id}"


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

    for r in recs:
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
    
def get_recent_memory(user_id, limit=20):
    rows = safe_query(
        """
        SELECT item_name, vendor_name
        FROM user_meal_memory
        WHERE telegram_id=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (str(user_id), limit),
        fetch=True
    )

    used_items = set()
    used_vendors = set()

    for r in rows:
        used_items.add(r[0])
        used_vendors.add(r[1])

    return used_items, used_vendors
# =========================
# SMART ENGINE
# =========================
def smart_recommend(user_id, meal, context=None):
    user = safe_get_user(user_id)
    if not user:
        return []

    items = get_menu_items()

    total_budget = int(user.get("budget", 1500))
    meals = parse_list(user.get("meals"))
    meal_count = len(meals) if meals else 2

    per_meal_budget = total_budget // meal_count
    allergies = parse_list(user.get("allergies") or "")

    filtered = [i for i in items if i["price"] <= per_meal_budget]

    filtered = [
        i for i in filtered
        if not any(a in i["item_name"].lower() for a in allergies)
    ]
    used_items, used_vendors = get_recent_memory(user_id)

    filtered = [
        i for i in filtered
        if i["item_name"] not in used_items
    ]
    if not filtered:
        filtered = [
            i for i in get_menu_items()
            if i["price"] <= per_meal_budget
        ]

    if not subscription_middleware(user_id):
        return random.sample(filtered, min(3, len(filtered)))

    global_scores = get_cached_vendor_scores() or {}
    user_scores = get_user_vendor_scores(user_id) or {}

    def score(item):
        price = item["price"]
        vendor = item["vendor_name"]

        price_score = per_meal_budget - price
        global_rating = global_scores.get(vendor, 3)
        user_rating = user_scores.get(vendor, 0)

        return price_score + (float(global_rating) * 10) + (float(user_rating) * 20)

    ranked = sorted(filtered, key=score, reverse=True)

    return ranked[:5]


# =========================
# MEAL TEXT BUILDER
# =========================
def build_meal_text(user_id, name, context=None, force_refresh=False):
    if not force_refresh:
        cached = get_cached_meal(user_id)
        if cached:
            return cached

    user = safe_get_user(user_id)
    if not user:
        return "User not found"

    meals = parse_list(user.get("meals"))
    selected = meals if meals else ["breakfast", "lunch"]

    total_budget = int(user.get("budget", 1500))
    per_meal_budget = total_budget // len(selected)

    text = f"🍽✨ {name}'s Smart Meal Plan\n\n"
    text += f"💰 Budget per meal: ₦{per_meal_budget}\n"

    total_cost = 0

    for meal in selected:
        recs = smart_recommend(user_id, meal, context)

        save_meal_memory(user_id, meal, recs)

        text += f"\n🍱 {meal.upper()} 🍱\n"

        for r in recs:
            text += f"✔ {r['vendor_name']} - {r['item_name']} - ₦{r['price']}\n"
            total_cost += int(r["price"])

    text += f"\n💰 TOTAL: ₦{total_cost}\n"

    set_cached_meal(user_id, text)

    return text
