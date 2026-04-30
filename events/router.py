from controllers.menu import handle_menu_text
from controllers.meals import reshuffle
from controllers.onboarding import start
from events.fsm_dispatcher import handle_fsm
from services.ai_service import ask_meal_ai
from user_service import subscription_middleware


async def route_callback(update, context):
    cq = update.callback_query
    await cq.answer()

    user_id = cq.from_user.id
    data = cq.data

    # GLOBAL ACTIONS
    if data.startswith("RESHUFFLE:"):
        return await reshuffle(update, context)

    # FSM HANDLING
    return await handle_fsm(update, context, user_id, data)


def route_message(update, context):
    text = update.message.text
    user_id = update.message.from_user.id

    AI_KEYWORDS = ["what", "meal", "eat", "food", "diet", "recommend", "suggest"]

    if subscription_middleware(user_id) and any(k in text.lower() for k in AI_KEYWORDS):
        ai_reply = ask_meal_ai(user_id, text)
        return update.message.reply_text(ai_reply)

    # normal routing continues below
    return handle_normal_routes(update, context)