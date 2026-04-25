from sheets import get_user, save_user, update_user, save_vendor_rating
from datetime import datetime, timedelta
from db import query
from cache import clear_cache
from datetime import datetime
from engine import smart_recommend  # reuse your engine
from tips import get_daily_tip


def build_daily_meal_message(user_id):
    user = get_user(user_id)
    if not user:
        return None

    name = user["name"]

    today = datetime.now().strftime("%A, %d %B %Y")

    meals = ["breakfast", "lunch", "dinner"]

    text = f"☀️ Good morning {name}!\n"
    text += f"📅 {today}\n\n"
    text += "🍽 Your BiteWise meal plan for today:\n\n"

    total = 0

    for meal in meals:
        recs = smart_recommend(user_id, meal)

        text += f"🍱 {meal.upper()}\n"

        for r in recs:
            text += f"- {r['vendor_name']} • {r['item_name']} (₦{r['price']})\n"
            total += int(r["price"])

        text += "\n"

    text += f"💰 Estimated total: ₦{total}\n\n"
    text += f"💡 Tip: {get_daily_tip()}"

    return text

# =========================
# CORE
# =========================
def safe_get_user(user_id):
    try:
        return get_user(user_id)
    except:
        return None


def get_or_create_user(user_id, name):
    user = safe_get_user(user_id)

    if not user:
        save_user(user_id, name, "free", 0)
        user = safe_get_user(user_id)

    return user


def save_state(user_id, **kwargs):
    update_user(user_id, **kwargs)


def get_state(user_id):
    user = safe_get_user(user_id)
    return user.get("state") if user else None


# =========================
# LIST HELPERS
# =========================
def parse_list(value):
    if not value:
        return []
    return value.split(",")


def save_list(user_id, field, values):
    update_user(user_id, **{field: ",".join(values)})


# =========================
# PREMIUM
# =========================
def is_premium(user_id):
    user = safe_get_user(user_id)
    return user and user.get("plan") == "premium"


def is_premium_active(user_id):
    user = safe_get_user(user_id)

    if not user or user.get("plan") != "premium":
        return False

    expiry = user.get("premium_expiry")
    if not expiry:
        return False

    try:
        expiry_date = datetime.fromisoformat(expiry)

        # 3 day grace period
        return datetime.utcnow() < expiry_date + timedelta(days=3)

    except:
        return False


def upgrade_user(user_id, plan="premium"):
    expiry = datetime.utcnow() + timedelta(days=7)

    update_user(
        user_id,
        plan=plan,
        premium_expiry=expiry.isoformat()
    )


def cancel_subscription(user_id):
    update_user(user_id, plan="free")


# =========================
# RATINGS
# =========================
def can_rate(user_id):
    return is_premium_active(user_id)




def rate_vendor(user_id, vendor, rating):
    if not can_rate(user_id):
        return False

    save_vendor_rating(user_id, vendor, rating)

    # 🔥 CLEAR USER CACHE
    clear_cache(f"user_scores:{user_id}")
    clear_cache("vendor_scores")

    return True

    save_vendor_rating(user_id, vendor, rating)
    return True