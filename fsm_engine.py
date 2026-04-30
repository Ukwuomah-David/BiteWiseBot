FSM = {}
TRANSITIONS = {}
from controllers.onboarding import (
    tithe_screen,
    welcome_screen,
    budget_screen,
    allergy_screen,
    meal_screen
)
FSM = {
    "TITHE": tithe_screen,
    "WELCOME": welcome_screen,
    "BUDGET": budget_screen,
    "ALLERGY": allergy_screen,
    "MEAL": meal_screen
}