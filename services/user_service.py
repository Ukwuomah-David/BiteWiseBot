from core import safe_get_user
from repositories.user_repo import update_user

class UserService:

    def update_budget(self, user_id, amount):
        if amount < 1500:
            return False, "Minimum is ₦1500"

        update_user(user_id, {"budget": amount})
        return True, "Updated"


    def update_allergies(self, user_id, allergies):
        update_user(user_id, {"allergies": str(allergies)})


    def update_meals(self, user_id, meals):
        update_user(user_id, {"meals": str(meals)})