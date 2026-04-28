from datetime import datetime, timedelta
from sheets import get_user
from engine import smart_recommend
from sheets import update_user
from cache import clear_cache
from tips import get_daily_tip
from core import (
    safe_get_user,
    get_or_create_user,
    save_state,
    get_state,
    parse_list,
    save_list
)
from db import query


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
# PREMIUM
# =========================
def engine.subscription_middleware(user_id):
    user = safe_get_user(user_id)
    return user and user.get("plan") == "premium"


def engine.subscription_middleware(user_id):
    user = safe_get_user(user_id)

    if not user or user.get("plan") != "premium":
        return False

    expiry = user.get("subscription_expires_at")
    if not expiry:
        return False

    try:
        expiry_date = datetime.fromisoformat(expiry)

        # 3 day grace period
        return datetime.utcnow() < expiry_date + timedelta(days=3)

    except:
        return False




def upgrade_user(user_id, plan="premium"):
    expiry = datetime.utcnow() + timedelta(days=30)

    query(
        """
        UPDATE users
        SET plan='premium', subscription_expires_at=%s
        WHERE telegram_id=%s
        """,
        (expiry.isoformat(), str(user_id))
    )


def cancel_subscription(user_id):
    update_user(user_id, plan="free")


# =========================
# RATINGS
# =========================
def can_rate(user_id):
    return engine.subscription_middleware(user_id)




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