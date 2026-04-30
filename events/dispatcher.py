from services.meal_service import generate_user_meals
from services.payment_service import handle_payment_event
from services.user_service import handle_user_event

async def handle_event(event):
    event_type = event.get("type")

    if event_type == "meal":
        return await generate_user_meals(event)

    if event_type == "payment":
        return await handle_payment_event(event)

    if event_type == "user":
        return await handle_user_event(event)
        