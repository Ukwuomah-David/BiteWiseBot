from core import safe_get_user, parse_list
import random

def generate_smart_meal(user_id, meal_type, history=[]):
    user = safe_get_user(user_id)

    allergies = parse_list(user.get("allergies"))
    budget = user.get("budget")

    base_meals = [
        "Jollof Rice", "Fried Rice", "Pasta", "Yam & Egg",
        "Beans & Plantain", "Suya Bowl", "Oatmeal"
    ]

    # filter logic
    filtered = [
        m for m in base_meals
        if m.lower() not in [a.lower() for a in allergies]
    ]

    # avoid repetition
    filtered = [m for m in filtered if m not in history]

    if not filtered:
        filtered = base_meals

    return random.choice(filtered)