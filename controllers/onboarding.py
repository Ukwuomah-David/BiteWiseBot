from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from core import safe_get_user, parse_list, save_list, get_or_create_user
from db import query as safe_query
from datetime import datetime, UTC
from fsm_engine import set_state, run_fsm, get_state
from user_service import subscription_middleware

# =========================
# STATES
# =========================
STATE_TITHE = "TITHE"
STATE_WELCOME = "WELCOME"
STATE_BUDGET = "BUDGET"
STATE_ALLERGY = "ALLERGY"
STATE_MEAL = "MEAL"


# =========================
# START ONBOARDING
# =========================
async def start(update, context):
    user_id = update.message.from_user.id
    name = update.message.from_user.first_name

    get_or_create_user(user_id, name)

    await update.message.reply_text(
        f"👋 {name}, ready to build financial discipline?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes", callback_data="tithe_yes"),
                InlineKeyboardButton("❌ No", callback_data="tithe_no")
            ]
        ])
    )

    if not get_state(user_id):
        set_state(user_id, STATE_TITHE)


# =========================
# TITHE SCREEN
# =========================
async def tithe_screen(update, context):
    cq = update.callback_query
    if not cq:
        return

    name = cq.from_user.first_name

    return await cq.edit_message_text(
        f"💰 {name}, do you commit to tithing 10%?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("I agree ✅", callback_data="tithe_yes"),
                InlineKeyboardButton("No ❌", callback_data="tithe_no")
            ]
        ])
    )


# =========================
# WELCOME SCREEN
# =========================
async def welcome_screen(update, context):
    cq = update.callback_query
    if not cq:
        return

    return await cq.edit_message_text(
        "🚀 Welcome to BiteWise!\n\nMeal planning + budget control 🍽💰",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Proceed", callback_data="proceed")]
        ])
    )


# =========================
# BUDGET SCREEN
# =========================
async def budget_screen(update, context):
    if update.message:
        user_id = update.message.from_user.id

        try:
            amount = int(update.message.text.strip())

            if amount < 1500:
                return await update.message.reply_text("❌ Minimum is ₦1500")

            safe_query(
                "UPDATE users SET budget=%s WHERE telegram_id=%s",
                (amount, str(user_id))
            )

            return await run_fsm(update, context)

        except:
            return await update.message.reply_text("❌ Enter a valid number")

    cq = update.callback_query
    if not cq:
        return

    return await cq.edit_message_text(
        "💰 Enter your daily budget (₦)\nMinimum: ₦1500"
    )


# =========================
# ALLERGY SCREEN
# =========================
async def allergy_state(update, context):
    cq = update.callback_query
    user_id = cq.from_user.id

    if cq.data.startswith("TOGGLE_ALLERGY:"):
        allergy = cq.data.split(":")[1]

        user = safe_get_user(user_id)
        allergies = parse_list(user.get("allergies"))

        if allergy in allergies:
            allergies.remove(allergy)
        else:
            allergies.append(allergy)

        save_list(user_id, "allergies", allergies)

    return await render_allergy_ui(cq, user_id)


async def render_allergy_ui(cq, user_id):
    user = safe_get_user(user_id)
    allergies = parse_list(user.get("allergies") or "")

    def mark(x): return "✔" if x in allergies else "○"

    text = "🤧 Select your allergies:\n\n"
    for a in ["nuts", "dairy", "spicy", "gluten", "seafood"]:
        text += f"{mark(a)} {a}\n"

    return await cq.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🥜 Nuts", callback_data="TOGGLE_ALLERGY:nuts"),
                InlineKeyboardButton("🥛 Dairy", callback_data="TOGGLE_ALLERGY:dairy")
            ],
            [
                InlineKeyboardButton("🌶 Spicy", callback_data="TOGGLE_ALLERGY:spicy"),
                InlineKeyboardButton("🍞 Gluten", callback_data="TOGGLE_ALLERGY:gluten")
            ],
            [
                InlineKeyboardButton("🐟 Seafood", callback_data="TOGGLE_ALLERGY:seafood")
            ],
            [
                InlineKeyboardButton("✅ Done", callback_data="allergy_done")
            ]
        ])
    )


# =========================
# MEAL SCREEN
# =========================
async def meal_state(update, context):
    cq = update.callback_query
    user_id = cq.from_user.id

    if cq.data.startswith("TOGGLE_MEAL:"):
        meal = cq.data.split(":")[1]

        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        if meal in meals:
            meals.remove(meal)
        else:
            meals.append(meal)

        save_list(user_id, "meals", meals)

    return await render_meal_ui(cq, user_id)


async def render_meal_ui(cq, user_id):
    user = safe_get_user(user_id)
    meals = parse_list(user.get("meals") or "")

    def mark(m): return "✔" if m in meals else "○"

    text = "🍽 Select your meals:\n\n"
    text += f"{mark('breakfast')} Breakfast\n"
    text += f"{mark('lunch')} Lunch\n"
    text += f"{mark('dinner')} Dinner\n"

    return await cq.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🍳 Breakfast", callback_data="TOGGLE_MEAL:breakfast"),
                InlineKeyboardButton("🍛 Lunch", callback_data="TOGGLE_MEAL:lunch"),
                InlineKeyboardButton("🍲 Dinner", callback_data="TOGGLE_MEAL:dinner")
            ],
            [InlineKeyboardButton("✅ Done", callback_data="meal_done")]
        ])
    )