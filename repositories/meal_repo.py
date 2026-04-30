from db import query as safe_query

def save_meal_preferences(user_id, meals):
    safe_query(
        "UPDATE users SET meals=%s WHERE telegram_id=%s",
        (str(meals), str(user_id))
    )