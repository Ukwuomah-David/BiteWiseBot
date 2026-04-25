from user_service import *
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from engine import build_meal_text, subscription_middleware
FSM = {}

def state(key):
    def wrapper(func):
        FSM[key] = func
        return func
    return wrapper


async def run_fsm(state, update, context):
    handler = FSM.get(state)

    if not handler:
        return None

    try:
        return await handler(update, context)
    except Exception as e:
        import logging
        logging.error(f"FSM ERROR [{state}]: {e}")
        return None

@state("MAIN_MENU")
async def main_menu(update, context):
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "🍽 My Meals":
        name = update.message.from_user.first_name
        return await update.message.reply_text(
            build_meal_text(user_id, name, context)
        )

    if text == "💰 Budget":
        save_state(user_id, state="BUDGET")
        return await update.message.reply_text("💰 Enter new budget:")

    if text == "🤧 Allergies":
        return await update.message.reply_text("Open allergy UI")

    if text == "💳 Subscription":
        active = subscription_middleware(user_id)
        return await update.message.reply_text(
            f"💳 {'Active' if active else 'Expired'}"
        )

    return await update.message.reply_text("⚠️ Unknown option")