import random

TIPS = [
    "Real wealth starts with controlling small daily spending decisions.",
    "Eating what fits your budget today is more powerful than peer pressure.",
    "Consistency beats motivation — stick to your meal plan even when friends don’t.",
    "Skipping expensive cravings today is how financial freedom starts tomorrow.",
    "Your budget is your discipline score — protect it.",
    "Peer pressure is temporary. Financial stress is long term.",
    "Smart people don’t eat to impress others, they eat to optimize life.",
    "Stick to your plan even when it feels boring — that's how winners are built.",
    "Small savings per meal compounds into financial freedom.",
    "Control food, control money, control future.",
    "Real discipline is choosing your budget even when others overspend around you.",
    "Your future wealth is built from the meals you say NO to today.",
    "Peer pressure is expensive — your budget is your identity.",
    "Stick to your meal plan even when others flex food choices.",
    "Skipping discipline today = financial stress tomorrow.",
    "BiteWise users don’t follow trends — they follow budgets.",
    "Control your food choices, control your financial future.",
    "Every meal you plan is a vote for your financial freedom.",
    "Consistency beats cravings. Always.",
    "The rich don’t eat randomly — they eat intentionally."
]

def get_daily_tip():
    return random.choice(TIPS)