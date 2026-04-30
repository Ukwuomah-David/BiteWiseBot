import engine
from telegram import InlineKeyboardButton
from core import safe_get_user
from user_service import subscription_middleware
from controllers.menu import get_main_menu

# =========================
# RESHUFFLE MEAL
# =========================
async def reshuffle(update, context):
    cq = update.callback_query
    await cq.answer()

    user_id = cq.from_user.id
    data = cq.data

    if not subscription_middleware(user_id):
        return await cq.answer("Upgrade required 🚫", show_alert=True)

    if ":" not in data:
        return await cq.answer("Invalid request", show_alert=True)

    _, meal = data.split(":")

    payload = engine.generate_meal_payload(user_id, meal, context)

    text_block = "🔄 " + payload["meal"].upper() + "\n\n" + payload["text"]

    keyboard = payload["buttons"]

    keyboard.append([
        InlineKeyboardButton("🔄 Reshuffle", callback_data=f"RESHUFFLE:{meal}")
    ])

    await cq.edit_message_text(
        text_block,
        reply_markup=keyboard
    )