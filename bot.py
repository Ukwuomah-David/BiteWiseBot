# =========================
# FIXED BOT.PY (STABLE BUILD)
# =========================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.error import BadRequest
from datetime import datetime, timedelta
from sheets import get_menu_items, get_vendor_scores, get_user_vendor_scores
from user_service import *
import logging
import random
import requests
from dotenv import load_dotenv
import os
from db import query
import uuid
import time

logging.basicConfig(level=logging.INFO)

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
# SIMPLE CACHE (IN-MEMORY)
# =========================
MEAL_CACHE = {}
CACHE_TTL = 15  # seconds
VENDOR_RANK_CACHE = {
    "data": {},
    "last_updated": 0
}

RANK_TTL = 300  # 5 minutes
# =========================
# PAYMENT
# =========================
def create_payment_link(user_id):
    reference = str(uuid.uuid4())

    query(
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

    query(
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
# ROUTING
# =========================
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
        try:
            await callback_query.message.reply_text(text, reply_markup=reply_markup)
        except:
            pass


# =========================
# PREFIX HANDLER (MISSING FIX)
# =========================
# =========================
# PREFIX HANDLER
# =========================
async def handle_prefix(update, context):
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name
    data = cq.data

    if data.startswith("a_"):
        allergy = data.replace("a_", "")
        user = safe_get_user(user_id)
        allergies = parse_list(user.get("allergies") or "")
        meals = parse_list(user.get("meals") or "")

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
def get_cache_key(user_id):
    return f"meal:{user_id}"


def get_cached_meal(user_id):
    key = get_cache_key(user_id)

    if key not in MEAL_CACHE:
        return None

    data, timestamp = MEAL_CACHE[key]

    # check expiry
    if time.time() - timestamp > CACHE_TTL:
        del MEAL_CACHE[key]
        return None

    return data


def set_cached_meal(user_id, value):
    key = get_cache_key(user_id)
    MEAL_CACHE[key] = (value, time.time())
def compute_vendor_ranks():
    """
    Precompute global vendor scores once every 5 minutes
    instead of querying DB per user request
    """

    global VENDOR_RANK_CACHE

    rows = get_vendor_scores()  # already SQL aggregated

    VENDOR_RANK_CACHE["data"] = rows
    VENDOR_RANK_CACHE["last_updated"] = time.time()

    return rows
def get_cached_vendor_scores():
    if (
        time.time() - VENDOR_RANK_CACHE["last_updated"]
        > RANK_TTL
    ):
        compute_vendor_ranks()

    return VENDOR_RANK_CACHE["data"]
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
    allergies = parse_list(user.get("allergies") or "")
    meals = parse_list(user.get("meals") or "")

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
    if not subscription_middleware(user_id):
        return random.sample(filtered, min(3, len(filtered)))
    
    # =========================
    # PREMIUM AI ENGINE (FIXED)
    # =========================
    global_scores = get_cached_vendor_scores() or {}
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

def get_today_meal(user_id):
    today = datetime.utcnow().date()

    rows = query(
        "SELECT message FROM daily_meals WHERE telegram_id=%s AND date=%s",
        (str(user_id), today),
        fetch=True
    )

    return rows[0][0] if rows else None
def subscription_middleware(user_id):
    user = safe_get_user(user_id)

    if not user:
        return False

    expiry = user.get("subscription_expires_at")

    if not expiry:
        return False

    expiry_date = datetime.fromisoformat(str(expiry))

    if datetime.utcnow() > expiry_date:
        # auto downgrade user
        query(
            "UPDATE users SET plan='free' WHERE telegram_id=%s",
            (str(user_id),)
        )
        return False

    return True
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
# MEAL BUILDER
# =========================
def build_meal_text(user_id, name, context=None, force_refresh=False):
    # =========================
    # CACHE CHECK
    # =========================
    if not force_refresh:
        cached = get_cached_meal(user_id)
        if cached:
            return cached
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

    # =========================
    # SAVE CACHE
    # =========================
    set_cached_meal(user_id, text)

    return text


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


# =========================
# ROUTES (UNCHANGED CORE)
# =========================
@route("ready_yes")
async def tithe_screen(update, context):
    data = update.callback_query.data
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name

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
    data = update.callback_query.data
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name
    save_state(user_id, state=STATE_WELCOME)

    return await safe_edit(
        query,
        "🚀 Welcome to BiteWise!\n\nMeal planning + budget control 🍽💰",
        InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Proceed", callback_data="proceed")]])
    )


@route("proceed")
async def budget_screen(update, context):
    data = update.callback_query.data
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name

    save_state(user_id, state=STATE_BUDGET)

    return await safe_edit(
        query,
        f"💰 {name}, enter your daily budget (₦)\nMinimum: ₦1500"
    )


@route("allergy_intro")
async def allergy_intro(update, context):
    cq = update.callback_query
    user_id = query.from_user.id
    name = cq.from_user.first_name
    save_state(user_id, state=STATE_ALLERGY)
    return await render_allergy_ui(query, user_id, query.from_user.first_name)


@route("allergy_done")
async def allergy_done(update, context):
    data = update.callback_query.data
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name
    save_state(user_id, state=STATE_MEAL)
    return await render_meal_ui(query, user_id, query.from_user.first_name)


@route("meal_done")
async def meal_done(update, context):
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    data = update.callback_query.data
    name = cq.from_user.first_name

    text = build_meal_text(user_id, name, context)

    buttons = [[InlineKeyboardButton("🔄 Reshuffle", callback_data="reshuffle")]]

    if not subscription_middleware(user_id):
        buttons.append([InlineKeyboardButton("💳 Upgrade", callback_data="upgrade")])

    # 🔥 IMPORTANT: attach menu AFTER onboarding completes
    # send menu separately
    await context.bot.send_message(
        chat_id=user_id,
        text="📋 Menu unlocked. Use it below 👇",
        reply_markup=get_main_menu()
    )

    # THEN edit original message
    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup(buttons)
    )




@route("reshuffle")
async def reshuffle(update, context):
    data = update.callback_query.data
    cq = update.callback_query
    query = cq
    user_id = cq.from_user.id
    name = cq.from_user.first_name
    if not subscription_middleware(user_id):
        return await query.answer("Upgrade required 🚫", show_alert=True)

    text = build_meal_text(
    user_id,
    query.from_user.first_name,
    context,
    force_refresh=True  # 🔥 bypass cache
)

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Reshuffle", callback_data="reshuffle")]])
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

    await update.message.reply_text(
        f"📋 Main Menu\nWelcome {name}",
        reply_markup=get_main_menu()
    )

    

# =========================
# MENU ROUTER
# =========================

MENU_ROUTES = {}
def menu_route(key):
    def wrapper(func):
        MENU_ROUTES[key] = func
        return func
    return wrapper
# =========================
# HANDLERS (UNCHANGED)
# =========================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # =========================
    # ROUTE FLOW SYSTEM
    # =========================
    if data in ROUTES:
        return await ROUTES[data](update, context)

    # =========================
    # MENU SYSTEM (NEW)
    # =========================
    if data in MENU_ROUTES:
        return await MENU_ROUTES[data](update, context)

    # fallback handlers
    if data.startswith("a_") or data.startswith("meal_"):
        return await handle_prefix(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    # =========================
    # MENU ROUTING (TEXT BUTTONS)
    # =========================
    if text == "📞 Support":
        return await update.message.reply_text(
            "📩 Support:\nEmail: support@bitewise.com\nPhone: +234-XXX-XXX"
        )

    if text == "🍳 Meal Times":
        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        return await update.message.reply_text(
            f"🍽 Current Meal Times:\n{meals}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Toggle Breakfast", callback_data="meal_breakfast")],
                [InlineKeyboardButton("Toggle Lunch", callback_data="meal_lunch")],
                [InlineKeyboardButton("Toggle Dinner", callback_data="meal_dinner")]
            ])
        )

    if text == "💳 Subscription":
        active = subscription_middleware(user_id)

        status = "✅ Active" if active else "❌ Expired"

        return await update.message.reply_text(
            f"💳 Subscription Status:\n{status}"
        )
    if text == "🍽 My Meals":
        name = update.message.from_user.first_name
        text_out = build_meal_text(user_id, name, context)

        return await update.message.reply_text(text_out)

    if text == "💰 Budget":
        save_state(user_id, state=STATE_BUDGET)
        return await update.message.reply_text("💰 Enter new budget:")

    if text == "🤧 Allergies":
        return await render_allergy_ui(
            update, user_id, update.message.from_user.first_name
        )

    if text == "🔄 Refresh Meal Plan":
        name = update.message.from_user.first_name

        text_out = build_meal_text(
            user_id,
            name,
            context,
            force_refresh=True
        )

        return await update.message.reply_text(text_out)
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
        
