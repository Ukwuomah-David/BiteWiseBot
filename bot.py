# =========================
# FIXED BOT.PY (STABLE BUILD)
# =========================
from dotenv import load_dotenv
load_dotenv()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest
from datetime import datetime, timedelta
import engine as engine
from db import query as safe_query
from fsm import state, FSM
from user_service import (
    build_daily_meal_message,
    rate_vendor,
    is_premium_active
)
import logging
import random
import requests
import os
import uuid
import time
import socket
socket.setdefaulttimeout(30)
logging.basicConfig(level=logging.INFO)
def get_cq(update):
    return getattr(update, "callback_query", None)

def get_user_id(update):
    cq = get_cq(update)
    return cq.from_user.id if cq else update.message.from_user.id
def build_inline_keyboard(buttons):
    keyboard = []

    for row in buttons:
        keyboard.append([
            InlineKeyboardButton(b["text"], callback_data=b["callback"])
            for b in row
        ])

    return InlineKeyboardMarkup(keyboard)
def get_user_name(update):
    cq = get_cq(update)
    return cq.from_user.first_name if cq else update.message.from_user.first_name
if not callable(query):
    raise Exception("DB query function not loaded properly")

load_dotenv(".env")

TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
PAYSTACK_LINK = "https://paystack.shop/pay/bitewise"

if not TOKEN:
    raise Exception("BOT_TOKEN missing")

if not PAYSTACK_SECRET:
    raise Exception("PAYSTACK_SECRET missing")

# =========================
# PAYMENT
# =========================
def create_payment_link(user_id):
    reference = str(uuid.uuid4())

    safe_query(
        "INSERT INTO payments (reference, telegram_id, amount, status) VALUES (%s,%s,%s,%s)",
        (reference, str(user_id), 100000, "pending")
    )

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json={
            "email": f"{user_id}@bitewise.bot",
            "amount": 100000,
            "reference": reference,
            "metadata": {"telegram_id": str(user_id)}
        },
        headers={
            "Authorization": f"Bearer {PAYSTACK_SECRET}",
            "Content-Type": "application/json"
        },
        timeout= 10
    )

    res_json = res.json()

    if not res_json.get("status"):
        logging.error(f"Paystack error: {res_json}")
        return None

    return res_json["data"]["authorization_url"]


# ✅ NEW: SUBSCRIPTION EXTENSION
def extend_subscription(user_id, days=30):
    user = safe_get_user(user_id)

    current = user.get("subscription_expires_at")

    if current:
        expiry = datetime.fromisoformat(str(current))
        if expiry > datetime.utcnow():
            expiry += timedelta(days=days)
        else:
            expiry = datetime.utcnow() + timedelta(days=days)
    else:
        expiry = datetime.utcnow() + timedelta(days=days)

    safe_query(
        "UPDATE users SET plan='premium', subscription_expires_at=%s WHERE telegram_id=%s",
        (expiry.isoformat(), str(user_id))
    )


# =========================
# STATES
# =========================
STATE_TITHE = "tithe"
STATE_WELCOME = "welcome"
STATE_BUDGET = "budget"
STATE_ALLERGY = "allergy"
STATE_MEAL = "meal"

# =========================
# SAFE EDIT
# =========================
async def safe_edit(callback_query, text, reply_markup=None):
    try:
        return await callback_query.edit_message_text(text, reply_markup=reply_markup)
    except BadRequest:
        try:
            await callback_query.message.reply_text(text, reply_markup=reply_markup)
        except:
            pass
   

# =========================
# ONBOARDING CHECK
# =========================

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




def get_today_meal(user_id):
    today = datetime.utcnow().date()

    rows = safe_query(
        "SELECT message FROM daily_meals WHERE telegram_id=%s AND date=%s",
        (str(user_id), today),
        fetch=True
    )

    return rows[0][0] if rows else None

def is_onboarding_complete(user_id):
    user = safe_get_user(user_id)

    if not user:
        return False

    return (
        user.get("budget") is not None and
        user.get("meals") is not None and
        user.get("allergies") is not None
    )


# =========================
# UI BUILDERS (UNCHANGED)
# =========================
async def render_allergy_ui(query, user_id, name):
    user = safe_get_user(user_id)
    allergies = parse_list(user.get("allergies") or "")
    meals = parse_list(user.get("meals") or "")

    def mark(x): return "✔" if x in allergies else "○"

    text = f"🤧 {name}, select your allergies:\n\n"
    for a in ["nuts", "dairy", "spicy", "gluten", "seafood"]:
        text += f"{mark(a)} {a.title()}\n"

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [InlineKeyboardButton("🥜 Nuts", callback_data="TOGGLE_ALLERGY:nuts"),
             InlineKeyboardButton("🥛 Dairy", callback_data="TOGGLE_ALLERGY:dairy")],
            [InlineKeyboardButton("🌶 Spicy", callback_data="TOGGLE_ALLERGY:spicy"),
             InlineKeyboardButton("🍞 Gluten", callback_data="TOGGLE_ALLERGY:gluten")],
            [InlineKeyboardButton("🐟 Seafood", callback_data="TOGGLE_ALLERGY:seafood")],
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
            [InlineKeyboardButton("🍳 Breakfast", callback_data="TOGGLE_MEAL:breakfast"),
             InlineKeyboardButton("🍛 Lunch", callback_data="TOGGLE_MEAL:lunch"),
             InlineKeyboardButton("🍲 Dinner", callback_data="TOGGLE_MEAL:dinner")],
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
    user_id = update.message.from_user.id

    msg = get_today_meal(user_id)

    if msg:
        await update.message.reply_text(msg)
        return
    await update.message.reply_text(
        f"👋 {name}, ready to build financial discipline?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data="ready_yes"),
             InlineKeyboardButton("❌ No", callback_data="tithe_no")]
        ])
    )

def safe_handler(fn):
    async def wrapper(update, context):
        try:
            return await fn(update, context)
        except Exception as e:
            logging.error(f"Handler crash {fn.__name__}: {e}")
            try:
                cq = update.callback_query
                if cq:
                    await cq.answer("Error occurred", show_alert=True)
            except:
                pass
    return wrapper
# =========================
# ROUTES (UNCHANGED CORE)
# =========================
@state("TITHE")
async def tithe_screen(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    name = get_user_name(update)
    data = update.callback_query.data
    

    save_state(user_id, state=STATE_TITHE)

    return await safe_edit(
        cq,
        f"💰 {name}, do you commit to tithing 10%?",
        InlineKeyboardMarkup([
            [InlineKeyboardButton("I agree ✅", callback_data="tithe_yes"),
             InlineKeyboardButton("No ❌", callback_data="tithe_no")]
        ])
    )


@state("WELCOME")
async def welcome_screen(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    name = get_user_name(update)
    data = update.callback_query.data
    save_state(user_id, state=STATE_WELCOME)

    return await safe_edit(
        cq,
        "🚀 Welcome to BiteWise!\n\nMeal planning + budget control 🍽💰",
        InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Proceed", callback_data="proceed")]])
    )


@state("BUDGET")
async def budget_screen(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    name = get_user_name(update)
    data = update.callback_query.data


    save_state(user_id, state=STATE_BUDGET)

    return await safe_edit(
        cq,
        f"💰 {name}, enter your daily budget (₦)\nMinimum: ₦1500"
    )


@state("ALLERGY")
async def allergy_state(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    data = cq.data

    if data.startswith("TOGGLE_ALLERGY:"):
        allergy = data.split(":")[1]

        user = safe_get_user(user_id)
        allergies = parse_list(user.get("allergies"))

        if allergy in allergies:
            allergies.remove(allergy)
        else:
            allergies.append(allergy)

        save_list(user_id, "allergies", allergies)

        return await render_allergy_ui(cq, user_id, get_user_name(update))

    if data == "allergy_done":
        save_state(user_id, state="MEAL")
        return await render_meal_ui(cq, user_id, get_user_name(update))

@state("MEAL")
async def meal_state(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    data = cq.data

    if data.startswith("TOGGLE_MEAL:"):
        meal = data.split(":")[1]

        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        if meal in meals:
            meals.remove(meal)
        else:
            meals.append(meal)

        save_list(user_id, "meals", meals)

        return await render_meal_ui(cq, user_id, get_user_name(update))

    if data == "meal_done":
        save_state(user_id, state="MAIN_MENU")

        await safe_edit(cq, "✅ Setup complete!")

        return await cq.message.reply_text(
            "📋 Main Menu",
            reply_markup=get_main_menu()
        )

@state("MAIN_MENU")
async def main_menu(update, context):
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    if text == "📞 Support":
        return await update.message.reply_text(
            "📩 Support:\nEmail: support@bitewise.com\nPhone: +234-XXX-XXX"
        )

    elif text == "🍳 Meal Times":
        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        return await update.message.reply_text(
            f"🍽 Current Meal Times:\n{meals}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Toggle Breakfast", callback_data="TOGGLE_MEAL:breakfast")],
                [InlineKeyboardButton("Toggle Lunch", callback_data="TOGGLE_MEAL:lunch")],
                [InlineKeyboardButton("Toggle Dinner", callback_data="TOGGLE_MEAL:dinner")]
            ])
        )

    elif text == "💳 Subscription":
        active = engine.subscription_middleware(user_id)
        status = "✅ Active" if active else "❌ Expired"

        return await update.message.reply_text(
            f"💳 Subscription Status:\n{status}"
        )

    elif text == "🍽 My Meals":
        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals")) or ["breakfast", "lunch"]

        for meal in meals:
            payload = engine.generate_meal_payload(user_id, meal, context)

            text_block = payload["text"]

            keyboard = build_inline_keyboard(payload["buttons"])

            # 🔥 PREMIUM FEATURE
            if engine.subscription_middleware(user_id):
                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(
                        "🔄 Reshuffle",
                        callback_data=f"RESHUFFLE:{meal}"
                    )
                ])

            await update.message.reply_text(
                text_block,
                reply_markup=keyboard
            )    

    elif text == "💰 Budget":
        save_state(user_id, state=STATE_BUDGET)
        return await update.message.reply_text("💰 Enter new budget:")

    elif text == "🤧 Allergies":
        return await update.message.reply_text(
            "Use buttons below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Allergies", callback_data="allergy_intro")]
            ])
        )

    else:
        return await update.message.reply_text("⚠️ Use menu buttons.")

async def open_allergy(update, context):
    cq = get_cq(update)
    data = cq.data

    if data == "allergy_intro":
        user_id = get_user_id(update)

        save_state(user_id, state="ALLERGY")
        return await render_allergy_ui(cq, user_id, get_user_name(update))
async def reshuffle(update, context):
    cq = get_cq(update)
    user_id = get_user_id(update)
    name = get_user_name(update)
    data = update.callback_query.data
    if not engine.subscription_middleware(user_id):
        return await cq.answer("Upgrade required 🚫", show_alert=True)

    _, meal = cq.data.split(":")

    payload = engine.generate_meal_payload(user_id, meal, context)

    text_block = "🔄 " + payload["meal"].upper() + " (Updated)\n\n" + payload["text"].split("\n\n", 1)[1]

    keyboard = build_inline_keyboard(payload["buttons"])

    keyboard.inline_keyboard.append([
        InlineKeyboardButton("🔄 Reshuffle", callback_data=f"RESHUFFLE:{meal}")
    ])

    return await safe_edit(
        cq,
        text_block,
        keyboard
    )
def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🍽 My Meals", "💰 Budget"],
            ["🤧 Allergies", "💳 Subscription"],
            ["🍳 Meal Times", "📞 Support"],
            ["🔄 Refresh Meal Plan"]
        ],
        resize_keyboard=True
    )
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name

    if not is_onboarding_complete(user_id):
        return await update.message.reply_text("⚠️ Complete onboarding first.")

    # ✅ SET FSM STATE HERE (CORRECT PLACE)
    save_state(user_id, state="MAIN_MENU")

    await update.message.reply_text(
        f"📋 Main Menu\nWelcome {name}",
        reply_markup=get_main_menu()
    )



# =========================
# HANDLERS (UNCHANGED)
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query

    try:
        await cq.answer()
    except:
        pass

    user_id = cq.from_user.id
    state = get_state(user_id)

    # ✅ GLOBAL BUTTONS (must be BEFORE state check)
    if cq.data == "allergy_intro":
        return await open_allergy(update, context)

    if cq.data.startswith("RESHUFFLE:"):
        return await reshuffle(update, context)
    if cq.data.startswith("LIKE:") or cq.data.startswith("DISLIKE:"):
        action, payload = cq.data.split(":")
        vendor, item = payload.split("|")

        value = 1 if action == "LIKE" else -1

        engine.save_feedback(user_id, item, vendor, value)

        responses = ["Got it 👍", "Learning... 🧠", "Nice choice 🔥", "Noted 👌"]
        await cq.answer(random.choice(responses))

    # ❗ THEN check state
    if not state:
        return await cq.message.reply_text("⚠️ Session expired. Type /start")

    handler = FSM.get(state)

    if not handler:
        return await cq.message.reply_text("⚠️ Unknown state")

    try:
        return await handler(update, context)
    except Exception as e:
        logging.error(f"FSM error: {e}")
        return await cq.message.reply_text("⚠️ Something went wrong")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    state = get_state(user_id)

    if not isinstance(state, str):
        logging.error(f"Invalid state: {state} for user {user_id}")
        return await update.message.reply_text("⚠️ Session error. Use /start")

    # =========================
    # FSM ROUTING
    # =========================
    handler = FSM.get(state)

    if handler:
        return await handler(update, context)

    
        
logging.info(f"Unhandled message state={state} user={user_id} text={text}")
# =========================
# MAIN (WEBHOOK MODE FIXED)
# =========================
def main():
    app = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Bot running (WEBHOOK MODE)...")

    app.run_polling()


if __name__ == "__main__":
    main()