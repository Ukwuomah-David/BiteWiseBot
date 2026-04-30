# =========================
# controllers/menu.py
# =========================

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import engine
from core import safe_get_user, parse_list
from user_service import subscription_middleware


# =========================
# HELPERS
# =========================
def get_user_id(update):
    if update.message:
        return update.message.from_user.id
    if update.callback_query:
        return update.callback_query.from_user.id
    return None


# =========================
# MAIN MENU ENTRY (FROM /menu COMMAND)
# =========================
async def main_menu(update, context):
    user_id = get_user_id(update)
    name = update.message.from_user.first_name if update.message else "User"

    user = safe_get_user(user_id)

    if not user:
        return await update.message.reply_text("⚠️ User not found. Use /start")

    if not user.get("budget") or not user.get("meals") or not user.get("allergies"):
        return await update.message.reply_text("⚠️ Complete onboarding first.")

    return await update.message.reply_text(
        f"📋 Main Menu\nWelcome {name}",
        reply_markup=get_main_menu_keyboard()
    )


# =========================
# REPLY KEYBOARD
# =========================
def get_main_menu_keyboard():
    from telegram import ReplyKeyboardMarkup

    return ReplyKeyboardMarkup(
        [
            ["🍽 My Meals", "💰 Budget"],
            ["🤧 Allergies", "💳 Subscription"],
            ["🍳 Meal Times", "📞 Support"],
            ["🔄 Refresh Meal Plan"]
        ],
        resize_keyboard=True
    )


# =========================
# MENU MESSAGE ROUTER
# =========================
async def menu_router(update, context):
    if not update.message:
        return

    text = update.message.text.strip()
    user_id = update.message.from_user.id

    # -------------------------
    # MY MEALS
    # -------------------------
    if text == "🍽 My Meals":

        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals")) or ["breakfast", "lunch"]

        for meal in meals:
            payload = engine.generate_meal_payload(user_id, meal, context)

            text_block = payload["text"]
            keyboard = build_keyboard(payload["buttons"])

            # PREMIUM FEATURE
            if subscription_middleware(user_id):
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

        return


    # -------------------------
    # BUDGET
    # -------------------------
    if text == "💰 Budget":
        return await update.message.reply_text(
            "💰 Your budget is stored. Use onboarding to change it."
        )


    # -------------------------
    # ALLERGIES
    # -------------------------
    if text == "🤧 Allergies":
        return await update.message.reply_text(
            "Manage allergies in onboarding:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Open Allergies", callback_data="allergy_intro")]
            ])
        )


    # -------------------------
    # SUBSCRIPTION
    # -------------------------
    if text == "💳 Subscription":

        active = subscription_middleware(user_id)

        status = "✅ Active" if active else "❌ Expired"

        return await update.message.reply_text(
            f"💳 Subscription Status:\n{status}"
        )


    # -------------------------
    # MEAL TIMES
    # -------------------------
    if text == "🍳 Meal Times":

        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals"))

        return await update.message.reply_text(
            f"🍽 Meal Times:\n{', '.join(meals)}"
        )


    # -------------------------
    # SUPPORT
    # -------------------------
    if text == "📞 Support":
        return await update.message.reply_text(
            "📩 Support:\nEmail: support@bitewise.com\nPhone: +234-XXX-XXX"
        )


    # -------------------------
    # REFRESH PLAN
    # -------------------------
    if text == "🔄 Refresh Meal Plan":

        user = safe_get_user(user_id)
        meals = parse_list(user.get("meals")) or ["breakfast"]

        for meal in meals:
            payload = engine.generate_meal_payload(user_id, meal, context)

            await update.message.reply_text(payload["text"])

        return


    return await update.message.reply_text("⚠️ Use menu buttons only.")


# =========================
# KEYBOARD BUILDER
# =========================
def build_keyboard(buttons):
    keyboard = []

    for row in buttons:
        keyboard.append([
            InlineKeyboardButton(b["text"], callback_data=b["callback"])
            for b in row
        ])

    return InlineKeyboardMarkup(keyboard)