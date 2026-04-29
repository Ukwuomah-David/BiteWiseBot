from fsm_engine import add_transition

# =========================
# TITHE
# =========================
add_transition("TITHE", "tithe_yes", "WELCOME")
add_transition("TITHE", "tithe_no", "WELCOME")

# =========================
# WELCOME
# =========================
add_transition("WELCOME", "proceed", "BUDGET")

# =========================
# BUDGET
# =========================
# (handled via message input, but keep fallback)
add_transition("BUDGET", "budget_done", "ALLERGY")

# =========================
# ALLERGY
# =========================
add_transition("ALLERGY", "allergy_done", "MEAL")

# =========================
# MEAL
# =========================
add_transition("MEAL", "meal_done", "MAIN_MENU")

# =========================
# MAIN MENU
# =========================
add_transition("MAIN_MENU", "🍽 My Meals", "MAIN_MENU")
add_transition("MAIN_MENU", "💰 Budget", "BUDGET")
add_transition("MAIN_MENU", "🤧 Allergies", "ALLERGY")
add_transition("MAIN_MENU", "📞 Support", "MAIN_MENU")
add_transition("MAIN_MENU", "💳 Subscription", "MAIN_MENU")

# =========================
# GLOBAL SAFETY (optional but smart)
# =========================
add_transition("ANY", "menu", "MAIN_MENU")