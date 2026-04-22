from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

from sheets import get_vendors, get_menu_items, get_user, save_user, update_user, save_vendor_rating
import random
import datetime
import requests

from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=".env")

TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
PAYSTACK_LINK = "https://paystack.shop/pay/bitewise"

if not TOKEN:
    raise Exception("BOT_TOKEN is missing. Check your .env or Render env vars.")


def create_payment_link(user_id, email=None):
    if not email:
        email = f"{user_id}@bitewise.bot"

    url = "https://api.paystack.co/transaction/initialize"
    

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    data = {
        "email": email,
        "amount": 100000,
        "metadata": {
            "telegram_id": str(user_id),
            "plan": "premium",
            "source": "bitewise_bot"
        },
        "callback_url": "https://bitewise-webhook.onrender.com/payment-success"
    }

    res = requests.post(url, json=data, headers=headers)

    try:
        response = res.json()
        return response["data"]["authorization_url"]
    except:
        return PAYSTACK_LINK

# =========================
# STATES
# =========================
STATE_START = "start"
STATE_TITHE = "tithe"
STATE_WELCOME = "welcome"
STATE_BUDGET = "budget"
STATE_ALLERGY = "allergy"
STATE_MEAL = "meal"
STATE_DONE = "done"

VALID_MEALS = {"breakfast", "lunch", "dinner"}

# =========================
# FSM ROUTER
# =========================
ROUTES = {}

def route(key):
    def wrapper(func):
        ROUTES[key] = func
        return func
    return wrapper


async def run_route(key, update, context):
    if key in ROUTES:
        return await ROUTES[key](update, context)

# =========================
# STATE STORE (PERSISTENT)
# =========================
def load_user(user_id):
    return get_user(user_id)

def save_state(user_id, **kwargs):
    update_user(user_id, **kwargs)

def get_state(user_id):
    user = get_user(user_id)
    return user.get("state") if user else None

def parse_list(value):
    if not value:
        return []
    return value.split(",")

def save_list(user_id, field, values):
    update_user(user_id, **{field: ",".join(values)})

# =========================
# SAFE EDIT
# =========================
async def safe_edit(query, text, reply_markup=None):
    try:
        return await query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise

# =========================
# SHEETS SAFE
# =========================
def safe_get_user(user_id):
    try:
        return get_user(user_id)
    except:
        return None

def upsert_user(user_id, name, plan="free", budget=0):
    user = safe_get_user(user_id)
    try:
        if user:
            update_user(user_id, plan=plan, budget=budget, name=name)
        else:
            save_user(user_id, name, plan, budget)
    except:
        pass

# =========================
# SMART ENGINE
# =========================
def smart_recommend(user_id, meal_type):
    user = safe_get_user(user_id)
    if not user:
        return []

    items = get_menu_items()
    budget = int(user.get("budget", 1500))
    plan = user.get("plan", "free")
    allergies = parse_list(user.get("allergies"))

    # 🔥 Filter by budget
    filtered = [i for i in items if i["price"] <= budget] or items

    # 🔥 Filter allergies (basic keyword filter)
    def is_safe(item):
        name = item["item_name"].lower()
        for a in allergies:
            if a in name:
                return False
        return True

    filtered = [i for i in filtered if is_safe(i)]

    if not filtered:
        filtered = items  # fallback

    # FREE USERS
    if plan == "free":
        return random.sample(filtered, min(3, len(filtered)))

    # PREMIUM USERS (sorted by price efficiency)
    filtered = sorted(filtered, key=lambda x: x["price"])
    return filtered[:5]
# =========================
# PLAN
# =========================
def is_premium(user_id):
    user = safe_get_user(user_id)
    return user and user.get("plan") == "premium"

def upgrade_user(user_id):
    update_user(user_id, plan="premium")

def cancel_subscription(user_id):
    update_user(user_id, plan="free")

# =========================
# MEAL BUILDER (FIXED)
# =========================
def build_meal_text(user_id, name):
    user = get_user(user_id)

    meals = parse_list(user.get("meals"))
    selected = meals if meals else ["breakfast", "lunch"]

    text = f"🍽✨ {name}'s Smart Meal Plan\n\n"

    total_cost = 0

    for meal in selected:
        recs = smart_recommend(user_id, meal)
        text += f"\n🍱 {meal.upper()} 🍱\n"

        for r in recs:
            text += f"✔ {r['vendor_name']} - {r['item_name']} - ₦{r['price']}\n"
            total_cost += int(r["price"])

    text += f"\n💰 TOTAL ESTIMATED COST: ₦{total_cost}\n"

    return text
# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name

    upsert_user(user_id, name)
    save_state(user_id, state=STATE_TITHE)

    await update.message.reply_text(
        f"👋 {name}, ready to build financial discipline?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data="ready_yes"),
                InlineKeyboardButton("❌ No", callback_data="tithe_no")
            ]
        ])
    )

async def render_allergy_ui(query, user_id, name):
    user = get_user(user_id)
    allergies = parse_list(user.get("allergies"))

    def mark(x): return "✔" if x in allergies else "○"

    text = f"🤧 {name}, select your allergies:\n\n"
    for a in ["nuts","dairy","spicy","gluten","seafood"]:
        text += f"{mark(a)} {a.title()}\n"

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🥜 Nuts", callback_data="a_nuts"),
                InlineKeyboardButton("🥛 Dairy", callback_data="a_dairy")
            ],
            [
                InlineKeyboardButton("🌶 Spicy", callback_data="a_spicy"),
                InlineKeyboardButton("🍞 Gluten", callback_data="a_gluten")
            ],
            [InlineKeyboardButton("🐟 Seafood", callback_data="a_seafood")],
            [InlineKeyboardButton("✅ Done", callback_data="allergy_done")]
        ])
    )

async def handle_allergy_toggle(user_id, query, name, data):
    allergy = data.replace("a_", "")
    user = get_user(user_id)
    allergies = parse_list(user.get("allergies"))

    if allergy in allergies:
        allergies.remove(allergy)
    else:
        allergies.append(allergy)

    save_list(user_id, "allergies", allergies)

    return await render_allergy_ui(query, user_id, name)

async def render_meal_ui(query, user_id, name):
    user = get_user(user_id)
    meals = parse_list(user.get("meals"))

    def mark(m): return "✔" if m in meals else "○"

    text = f"🍽 {name}, select your meals:\n\n"
    text += f"{mark('breakfast')} Breakfast\n"
    text += f"{mark('lunch')} Lunch\n"
    text += f"{mark('dinner')} Dinner\n"

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍳 Breakfast", callback_data="meal_breakfast"),
                InlineKeyboardButton("🍛 Lunch", callback_data="meal_lunch"),
                InlineKeyboardButton("🍲 Dinner", callback_data="meal_dinner")
            ],
            [InlineKeyboardButton("✅ Done", callback_data="meal_done")]
        ])
    )

# =========================
# ROUTES
# =========================
@route("ready_yes")
async def tithe_screen(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    save_state(user_id, state=STATE_TITHE)

    return await safe_edit(
        query,
        f"💰 {name}, do you commit to tithing 10% of your income?",
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton("I agree ✅", callback_data="tithe_yes"),
                InlineKeyboardButton("No ❌", callback_data="tithe_no")
            ]
        ])
    )

@route("tithe_yes")
async def welcome_screen(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_WELCOME)

    return await safe_edit(
        query,
        "🚀 Welcome to BiteWise!\n\n"
        "I help you plan your meals 7 days a week 🍽\n"
        "while keeping you within your budget 💰",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Proceed", callback_data="proceed")]
        ])
    )

@route("proceed")
async def budget_screen(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    save_state(user_id, state=STATE_BUDGET)

    return await safe_edit(
        query,
        f"💰 {name}, enter your daily budget (₦)\n\n"
        "📌 Minimum: ₦1500"
    )

@route("allergy_intro")
async def allergy_intro(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_ALLERGY)

    return await render_allergy_ui(query, user_id, query.from_user.first_name)

@route("allergy_done")
async def allergy_done(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_MEAL)

    return await render_meal_ui(query, user_id, query.from_user.first_name)

@route("meal_done")
async def meal_done(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    text = build_meal_text(user_id, name)

    if is_premium(user_id):
        buttons = [[InlineKeyboardButton("🔄 Reshuffle", callback_data="reshuffle")]]
    else:
        buttons = [[InlineKeyboardButton("💳 Upgrade to Premium", callback_data="upgrade")]]

    return await safe_edit(query, text, InlineKeyboardMarkup(buttons))
@route("go_back")
async def go_back(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_BUDGET)

    return await safe_edit(
        query,
        "🔙 Enter your budget again:"
    )
@route("upgrade")
async def upgrade(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    link = create_payment_link(user_id)

    return await safe_edit(
        query,
        "💳 Complete your payment below:",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("Pay Now", url=link)]
        ])
    )
@route("reshuffle")
async def reshuffle(update, context):
    query = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    if not is_premium(user_id):
        return await query.answer("Upgrade to use reshuffle 🚫", show_alert=True)

    text = build_meal_text(user_id, name)

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Reshuffle Again", callback_data="reshuffle")]
        ])
    )
# =========================
# PREFIX HANDLER
# =========================
async def handle_prefix(update, context):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    name = query.from_user.first_name

    if data.startswith("a_"):
        return await handle_allergy_toggle(user_id, query, name, data)

    if data.startswith("meal_"):
        meal = data.replace("meal_", "")
        user = get_user(user_id)
        meals = parse_list(user.get("meals"))

        if meal in meals:
            meals.remove(meal)
        else:
            meals.append(meal)

        save_list(user_id, "meals", meals)

        return await render_meal_ui(query, user_id, name)

# =========================
# BUTTON HANDLER
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data in ROUTES:
        return await ROUTES[data](update, context)

    if data.startswith("a_") or data.startswith("meal_"):
        return await handle_prefix(update, context)

# =========================
# MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name
    text = update.message.text.strip()

    state = get_state(user_id)

    if state == STATE_BUDGET:

        # ❌ INVALID INPUT (not a number)
        if not text.isdigit():
            return await update.message.reply_text(
                "❌ Invalid number! Please enter a valid budget amount in digits.\n"
                "Example: 2000 💰"
            )

        budget = int(text)

        # ❌ BELOW MINIMUM
        if budget < 1500:
            return await update.message.reply_text(
                "⚠️ Minimum budget is ₦1500 💰\n"
                "Please enter ₦1500 or above to continue."
            )

        # ✅ VALID INPUT
        save_state(user_id, budget=budget, state=STATE_ALLERGY)

        return await update.message.reply_text(
            "✅ Budget set successfully! 💰✨\n\n"
            "Now continue to allergies 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Continue ➡️", callback_data="allergy_intro")]
            ])
        )
# =========================
# MAIN
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
