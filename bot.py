
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest

from sheets import get_menu_items, get_vendor_scores, get_user_vendor_scores
from user_service import *
import logging
logging.basicConfig(level=logging.INFO)
import random
import requests
from dotenv import load_dotenv
import os
from db import query
import uuid
if not callable(query):
    raise Exception("DB query function not loaded properly")
load_dotenv(dotenv_path=".env")

TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
PAYSTACK_LINK = "https://paystack.shop/pay/bitewise"


# =========================
# PAYMENT
# =========================
def create_payment_link(user_id):
    reference = str(uuid.uuid4())

    query(
        "INSERT INTO payments (reference, telegram_id, amount, status) VALUES (%s,%s,%s,%s)",
        (reference, str(user_id), 100000, "pending")
    )

    url = "https://api.paystack.co/transaction/initialize"

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    data = {
        "email": f"{user_id}@bitewise.bot",
        "amount": 100000,
        "reference": reference,
        "metadata": {
            "telegram_id": str(user_id)
        }
    }

    res = requests.post(url, json=data, headers=headers)
    return res.json()["data"]["authorization_url"]


# =========================
# STATES
# =========================
STATE_TITHE = "tithe"
STATE_WELCOME = "welcome"
STATE_BUDGET = "budget"
STATE_ALLERGY = "allergy"
STATE_MEAL = "meal"

ROUTES = {}


def route(key):
    def wrapper(func):
        ROUTES[key] = func
        return func
    return wrapper


# =========================
# SAFE EDIT
# =========================
async def safe_edit(callback_query, text, reply_markup=None):
    try:
        return await callback_query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest:
        return


# =========================
# SMART ENGINE HELPERS (FIXED)
# =========================
# =========================
# PREFIX HANDLER (MISSING FIX)
# =========================
async def handle_prefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    data = query.data
    user_id = query.from_user.id
    name = query.from_user.first_name

    if data.startswith("a_"):
        allergy = data.replace("a_", "")
        user = safe_get_user(user_id)
        allergies = parse_list(user.get("allergies"))

        if allergy in allergies:
            allergies.remove(allergy)
        else:
            allergies.append(allergy)

        save_list(user_id, "allergies", allergies)
        return await render_allergy_ui(query, user_id, name)

    if data.startswith("meal_"):
        meal = data.replace("meal_", "")
        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        if meal in meals:
            meals.remove(meal)
        else:
            meals.append(meal)

        save_list(user_id, "meals", meals)
        return await render_meal_ui(query, user_id, name)

def get_seen_vendors(context):
    if context and context.user_data.get("seen_vendors"):
        return set(context.user_data["seen_vendors"])
    return set()


def update_seen_vendors(context, vendors):
    if context is None:
        return

    used = context.user_data.get("seen_vendors", [])

    for v in vendors:
        if v not in used:
            used.append(v)

    context.user_data["seen_vendors"] = used[-8:]


# =========================
# SMART ENGINE (FIXED + SAFE)
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
    allergies = parse_list(user.get("allergies"))

    # FILTER
    filtered = [i for i in items if i["price"] <= per_meal_budget]

    filtered = [
        i for i in filtered
        if not any(a in i["item_name"].lower() for a in allergies)
    ]

    if not filtered:
        filtered = items

    # =========================
    # FREE USERS
    # =========================
    if not is_premium_active(user_id):
        return random.sample(filtered, min(3, len(filtered)))

    # =========================
    # PREMIUM AI ENGINE (FIXED)
    # =========================
    global_scores = get_vendor_scores() or {}
    user_scores = get_user_vendor_scores(user_id) or {}

    seen_vendors = get_seen_vendors(context)

    def score(item):
        price = item["price"]
        vendor = item["vendor_name"]

        price_score = (per_meal_budget - price)

        global_rating = global_scores.get(vendor, 3)
        user_rating = user_scores.get(vendor, 0)

        repetition_penalty = -10 if vendor in seen_vendors else 0
        exploration_bonus = 8 if vendor not in seen_vendors else 0

        mood = random.uniform(-2, 2)

        return (
            price_score * 0.3 +
            global_rating * 15 +
            user_rating * 25 +
            repetition_penalty +
            exploration_bonus +
            mood
        )

    ranked = sorted(filtered, key=score, reverse=True)

    update_seen_vendors(context, [i["vendor_name"] for i in ranked[:5]])

    return ranked[:5]


# =========================
# MEAL BUILDER
# =========================
def build_meal_text(user_id, name, context=None):
    user = safe_get_user(user_id)

    meals = parse_list(user.get("meals"))
    selected = meals if meals else ["breakfast", "lunch"]

    total_budget = int(user.get("budget", 1500))
    per_meal_budget = total_budget // len(selected)

    text = f"🍽✨ {name}'s Smart Meal Plan\n\n"
    text += f"💰 Budget per meal: ₦{per_meal_budget}\n"

    total_cost = 0

    for meal in selected:
        recs = smart_recommend(user_id, meal, context)

        text += f"\n🍱 {meal.upper()} 🍱\n"

        for r in recs:
            text += f"✔ {r['vendor_name']} - {r['item_name']} - ₦{r['price']}\n"
            total_cost += int(r["price"])

    text += f"\n💰 TOTAL ESTIMATED COST: ₦{total_cost}\n"
    return text


# =========================
# UI BUILDERS (UNCHANGED)
# =========================
async def render_allergy_ui(query, user_id, name):
    user = safe_get_user(user_id)
    allergies = parse_list(user.get("allergies"))

    def mark(x): return "✔" if x in allergies else "○"

    text = f"🤧 {name}, select your allergies:\n\n"
    for a in ["nuts", "dairy", "spicy", "gluten", "seafood"]:
        text += f"{mark(a)} {a.title()}\n"

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🥜 Nuts", callback_data="a_nuts"),
             InlineKeyboardButton("🥛 Dairy", callback_data="a_dairy")],
            [InlineKeyboardButton("🌶 Spicy", callback_data="a_spicy"),
             InlineKeyboardButton("🍞 Gluten", callback_data="a_gluten")],
            [InlineKeyboardButton("🐟 Seafood", callback_data="a_seafood")],
            [InlineKeyboardButton("✅ Done", callback_data="allergy_done")]
        ])
    )


async def render_meal_ui(query, user_id, name):
    user = safe_get_user(user_id)
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
            [InlineKeyboardButton("🍳 Breakfast", callback_data="meal_breakfast"),
             InlineKeyboardButton("🍛 Lunch", callback_data="meal_lunch"),
             InlineKeyboardButton("🍲 Dinner", callback_data="meal_dinner")],
            [InlineKeyboardButton("✅ Done", callback_data="meal_done")]
        ])
    )


# =========================
# START (UNCHANGED)
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name

    get_or_create_user(user_id, name)
    save_state(user_id, state=STATE_TITHE)

    await update.message.reply_text(
        f"👋 {name}, ready to build financial discipline?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="ready_yes"),
             InlineKeyboardButton("❌ No", callback_data="tithe_no")]
        ])
    )


# =========================
# ROUTES (UNCHANGED CORE)
# =========================
@route("ready_yes")
async def tithe_screen(update, context):
    cq = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    save_state(user_id, state=STATE_TITHE)

    return await safe_edit(
        query,
        f"💰 {name}, do you commit to tithing 10%?",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("I agree ✅", callback_data="tithe_yes"),
             InlineKeyboardButton("No ❌", callback_data="tithe_no")]
        ])
    )


@route("tithe_yes")
async def welcome_screen(update, context):
    cq = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_WELCOME)

    return await safe_edit(
        query,
        "🚀 Welcome to BiteWise!\n\nMeal planning + budget control 🍽💰",
        InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Proceed", callback_data="proceed")]])
    )


@route("proceed")
async def budget_screen(update, context):
    cq = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    save_state(user_id, state=STATE_BUDGET)

    return await safe_edit(
        query,
        f"💰 {name}, enter your daily budget (₦)\nMinimum: ₦1500"
    )


@route("allergy_intro")
async def allergy_intro(update, context):
    cq = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_ALLERGY)
    return await render_allergy_ui(query, user_id, query.from_user.first_name)


@route("allergy_done")
async def allergy_done(update, context):
    cq = update.callback_query
    user_id = query.from_user.id

    save_state(user_id, state=STATE_MEAL)
    return await render_meal_ui(query, user_id, query.from_user.first_name)


@route("meal_done")
async def meal_done(update, context):
    cq = update.callback_query
    user_id = query.from_user.id
    name = query.from_user.first_name

    text = build_meal_text(user_id, name, context)

    buttons = [[InlineKeyboardButton("🔄 Reshuffle", callback_data="reshuffle")]]

    if not is_premium_active(user_id):
        buttons.append([InlineKeyboardButton("💳 Upgrade", callback_data="upgrade")])

    return await safe_edit(query, text, InlineKeyboardMarkup(buttons))


@route("upgrade")
async def upgrade(update, context):
    cq = update.callback_query
    user_id = query.from_user.id

    link = create_payment_link(user_id)

    return await safe_edit(
        query,
        "💳 Complete payment:",
        InlineKeyboardMarkup([[InlineKeyboardButton("Pay Now", url=link)]])
    )


@route("reshuffle")
async def reshuffle(update, context):
    cq = update.callback_query
    user_id = query.from_user.id

    if not is_premium_active(user_id):
        return await query.answer("Upgrade required 🚫", show_alert=True)

    text = build_meal_text(user_id, query.from_user.first_name, context)

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Again", callback_data="reshuffle")]])
    )


# =========================
# HANDLERS (UNCHANGED)
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    await query.answer()

    data = query.data

    if data in ROUTES:
        return await ROUTES[data](update, context)

    if data.startswith("a_") or data.startswith("meal_"):
        return await handle_prefix(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    state = get_state(user_id)

    if state == STATE_BUDGET:
        if not text.isdigit():
            return await update.message.reply_text("❌ Invalid number")

        budget = int(text)

        if budget < 1500:
            return await update.message.reply_text("⚠️ Minimum ₦1500")

        save_state(user_id, budget=budget, state=STATE_ALLERGY)

        return await update.message.reply_text(
            "✅ Budget saved!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Continue ➡️", callback_data="allergy_intro")]
            ])
        )


# =========================
# MAIN (WEBHOOK MODE FIXED)
# =========================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running (WEBHOOK MODE)...")

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=os.getenv("WEBHOOK_URL")
    )


if __name__ == "__main__":
    main()