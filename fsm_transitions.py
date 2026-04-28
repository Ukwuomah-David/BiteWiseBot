from fsm_engine import add_transition


# TITHE
add_transition("TITHE", "tithe_yes", "WELCOME")
add_transition("TITHE", "tithe_no", "WELCOME")

# WELCOME
add_transition("WELCOME", "proceed", "BUDGET")

# ALLERGY FLOW
add_transition("ALLERGY", "allergy_done", "MEAL")

# MEAL FLOW
add_transition("MEAL", "meal_done", "MAIN_MENU")

# GLOBAL RECOVERY
add_transition("MAIN_MENU", "🍽 My Meals", "MAIN_MENU")
add_transition("MAIN_MENU", "💰 Budget", "BUDGET")
add_transition("MAIN_MENU", "🤧 Allergies", "ALLERGY")