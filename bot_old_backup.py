from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest
from telegram.error import BadRequest

from sheets import get_vendors, get_menu_items, get_user, save_user, update_user, save_vendor_rating
import random
import datetime

TOKEN = "8656987123:AAHO9zQjEwLoqSVI9VB1WMKr3t_z9zderSA"
PAYSTACK_LINK = "https://paystack.com/pay/YOUR_LINK"

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
# STATE MACHINE STORE
# =========================
user_state = {}

def ensure_user_state(user_id):
    if user_id not in user_state:
        user_state[user_id] = {
            "state": STATE_START,
            "lock": False,
            "data": {
                "tithe": None,
                "budget": 0,
                "allergies": [],
                "meals": {
                    "breakfast": False,
                    "lunch": False,
                    "dinner": False
                }
            }
        }

def set_state(user_id, state):
    user_state[user_id]["state"] = state

def get_state(user_id):
    return user_state[user_id]["state"]

def get_data(user_id):
    return user_state[user_id]["data"]

def lock(user_id):
    user_state[user_id]["lock"] = True

def unlock(user_id):
    user_state[user_id]["lock"] = False

def is_locked(user_id):
    return user_state[user_id]["lock"]

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
# SAFE SHEETS
# =========================
def safe_get_user(user_id):
    try:
        return get_user(user_id)
    except Exception as e:
        print("Sheets error:", e)
        return None

def upsert_user(user_id, name, plan="free", budget=0):
    user = safe_get_user(user_id)
    try:
        if user:
            update_user(user_id, plan=plan, budget=budget, name=name)
        else:
            save_user(user_id, name, plan, budget)
    except Exception as e:
        print("Write failed:", e)

# =========================
# SMART ENGINE
# =========================
def smart_recommend(user_id, meal_type):
    user = safe_get_user(user_id)
    if not user:
        return []

    vendors = get_vendors()
    items = get_menu_items()

    budget = int(user.get("budget", 1500))
    plan = user.get("plan", "free")

    filtered_items = [
        i for i in items if i["price"] <= budget
    ] or items

    if plan == "free":
        return random.sample(filtered_items, min(5, len(filtered_items)))

    return filtered_items[:5]

# =========================
# BUILD MEALS
# =========================
def build_meal_text(user_id, name):
    data = get_data(user_id)
    selected = [m for m, v in data["meals"].items() if v] or ["breakfast", "lunch"]

    text = f"🍽 {name}'s Smart Meal Plan\n\n"

    for meal in selected:
        recs = smart_recommend(user_id, meal)
        text += f"\n🍱 {meal.title()}\n"
        for r in recs:
            text += f"✔ {r['vendor_name']} - {r['item_name']} - ₦{r['price']}\n"

    return text

# =========================
# UI
# =========================
async def render_meal_ui(query, user_id, name):
    data = get_data(user_id)

    text = f"{name}, select your meals:\n\n"
    text += f"{'✔' if data['meals']['breakfast'] else '○'} Breakfast\n"
    text += f"{'✔' if data['meals']['lunch'] else '○'} Lunch\n"
    text += f"{'✔' if data['meals']['dinner'] else '○'} Dinner\n"

    return await safe_edit(
        query,
        text,
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍳 Breakfast", callback_data="meal_breakfast"),
                InlineKeyboardButton("🍛 Lunch", callback_data="meal_lunch"),
                InlineKeyboardButton("🍲 Dinner", callback_data="meal_dinner")
            ],
            [InlineKeyboardButton("✅ Done", callback_data="meal_done")],
            [InlineKeyboardButton("⬅️ Back", callback_data="go_back")]
        ])
    )

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name

    ensure_user_state(user_id)
    upsert_user(user_id, name)

    set_state(user_id, STATE_TITHE)

    await update.message.reply_text(
        f"{name}, are you ready to build financial discipline?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data="ready_yes"),
                InlineKeyboardButton("❌ No", callback_data="ready_no")
            ]
        ])
    )
async def render_allergy_intro(query, user_id, name):
    return await safe_edit(
        query,
        f"{name}, do you have any allergies? (Optional)",
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🥜 Yes, I do", callback_data="allergy_yes"),
                InlineKeyboardButton("➡️ Skip", callback_data="allergy_done")
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="go_back")]
        ])
    )
async def render_allergy_ui(query, user_id, name):
    allergies = get_data(user_id)["allergies"]

    def mark(x):
        return "✔" if x in allergies else "○"

    text = f"{name}, select your allergies:\n\n"
    text += f"{mark('nuts')} Nuts\n"
    text += f"{mark('dairy')} Dairy\n"
    text += f"{mark('spicy')} Spicy\n"
    text += f"{mark('gluten')} Gluten\n"
    text += f"{mark('seafood')} Seafood\n"

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
            [InlineKeyboardButton("✅ Done", callback_data="allergy_done")],
            [InlineKeyboardButton("⬅️ Back", callback_data="go_back")]
        ])
    )
# =========================
# BUTTON HANDLER (FSM UPGRADED)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    name = query.from_user.first_name
    data = query.data

    ensure_user_state(user_id)

    # LOCK FIX (allow allergy interaction)
    if is_locked(user_id) and not (
        data.startswith("a_") or data in ["allergy_done", "go_back"]
    ):
        return await query.answer("Please wait...")

    # =========================
    # READY
    # =========================
    if data == "ready_yes":
        set_state(user_id, STATE_TITHE)
        return await safe_edit(
            query,
            f"{name}, do you commit to tithing-10% of your income",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("I agree", callback_data="tithe_yes"),
                    InlineKeyboardButton("No", callback_data="tithe_no")
                ]
            ])
        )

    # ✅ FIX 1: HANDLE NO
    if data == "tithe_no":
        return await query.answer(
            "BiteWise requires your commitment to proceed.",
            show_alert=True
        )

    # =========================
    # TITHE → WELCOME
    # =========================
    if data == "tithe_yes":
        set_state(user_id, STATE_TITHE)  # keep your structure intact
        return await safe_edit(
            query,
            "Welcome to BiteWise\n\nI help you plan your meals 7-days a week, while keeping to your budget.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("Proceed", callback_data="proceed")]
            ])
        )

    # =========================
    # WELCOME → BUDGET
    # =========================
    if data == "proceed":
        set_state(user_id, STATE_BUDGET)
        return await safe_edit(query, f"{name}, enter your daily budget (₦):")

    # =========================
    # ALLERGY INTRO (RESTORED)
    # =========================
    if data == "allergy_intro":
        unlock(user_id)  # ✅ critical fix
        set_state(user_id, STATE_ALLERGY)
        return await render_allergy_intro(query, user_id, name)

    # =========================
    # ALLERGY START
    # =========================
    if data == "allergy_yes":
        set_state(user_id, STATE_ALLERGY)
        lock(user_id)
        return await render_allergy_ui(query, user_id, name)

    # =========================
    # TOGGLE ALLERGIES (FIXED)
    # =========================
    if data.startswith("a_"):
        allergy = data.replace("a_", "")
        allergies = get_data(user_id)["allergies"]

        if allergy in allergies:
            allergies.remove(allergy)
        else:
            allergies.append(allergy)

        return await render_allergy_ui(query, user_id, name)

    if data == "allergy_done":
        unlock(user_id)
        set_state(user_id, STATE_MEAL)
        return await render_meal_ui(query, user_id, name)

    # =========================
    # MEALS (FIXED)
    # =========================
    if data.startswith("meal_") and data != "meal_done":
        meal = data.replace("meal_", "")
        if meal in get_data(user_id)["meals"]:
            get_data(user_id)["meals"][meal] = not get_data(user_id)["meals"][meal]
        return await render_meal_ui(query, user_id, name)

    if data == "meal_done":
        text = build_meal_text(user_id, name)

        return await safe_edit(
            query,
            text,
            InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Reshuffle", callback_data="reshuffle")],
                [InlineKeyboardButton("⭐ Rate Vendors", callback_data="rate_start")],
                [InlineKeyboardButton("💳 Upgrade to Premium", url=PAYSTACK_LINK)]
            ])
        )

    # =========================
    # BACK BUTTON (FULL FIX)
    # =========================
    if data == "go_back":
        state = get_state(user_id)

        if state == STATE_ALLERGY:
            unlock(user_id)  # ✅ IMPORTANT
            set_state(user_id, STATE_BUDGET)
            return await safe_edit(query, f"{name}, enter your daily budget (₦):")

        if state == STATE_MEAL:
            unlock(user_id)  # ensure buttons are responsive
            set_state(user_id, STATE_ALLERGY)
            return await render_allergy_intro(query, user_id, name)

        if state == STATE_BUDGET:
            set_state(user_id, STATE_TITHE)
            return await safe_edit(
                query,
                f"{name}, do you commit to tithing-10% of your income",
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("I agree", callback_data="tithe_yes"),
                        InlineKeyboardButton("No", callback_data="tithe_no")
                    ]
                ])
            )

# =========================
# MESSAGE
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name
    text = update.message.text

    ensure_user_state(user_id)

    if get_state(user_id) == STATE_BUDGET:
        if not text.isdigit():
            return await update.message.reply_text("Enter a valid number")

        budget = int(text)

        # ✅ MINIMUM BUDGET FIX
        if budget < 1500:
            return await update.message.reply_text(
                "Minimum budget is ₦1500.\nPlease enter a higher amount."
            )

        get_data(user_id)["budget"] = budget

        upsert_user(user_id, name, "free", budget)

        # ✅ IMPORTANT: KEEP STATE CLEAN
        set_state(user_id, STATE_ALLERGY)

        return await update.message.reply_text(
            f"Nice {name}. Budget set to ₦{budget}\n\n"
            "Your budget will be intelligently shared across the meal times you select.\n\n"
            "Now continue 👇",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Continue", callback_data="allergy_intro")]
            ])
        )

# =========================
# MAIN
# =========================
def main():
    print("Starting bot...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()