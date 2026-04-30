from core import safe_get_user
from repositories.meal_repo import save_meal_preferences
import engine

class MealService:

    async def generate_meal(self, user_id, meal_type, context):
        user = safe_get_user(user_id)

        payload = engine.generate_meal_payload(user_id, meal_type, context)

        return payload


    async def reshuffle_meal(self, user_id, meal_type, context):
        payload = engine.generate_meal_payload(user_id, meal_type, context)

        return {
            "meal": meal_type,
            "text": payload["text"],
            "buttons": payload["buttons"]
        }