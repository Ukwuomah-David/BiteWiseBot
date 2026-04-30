from openai import OpenAI
import os
from core import safe_get_user, parse_list

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_user_context(user_id):
    user = safe_get_user(user_id)

    return {
        "budget": user.get("budget"),
        "allergies": parse_list(user.get("allergies")),
        "meals": parse_list(user.get("meals")),
        "plan": user.get("plan"),
    }


def ask_meal_ai(user_id, message):
    context = build_user_context(user_id)

    prompt = f"""
You are a personal meal assistant inside a food SaaS app.

User profile:
- Budget: {context['budget']}
- Allergies: {context['allergies']}
- Meals per day: {context['meals']}
- Plan: {context['plan']}

User request:
{message}

Rules:
- Always respect allergies
- Always respect budget
- Prefer Nigerian/local meals when possible
- Be concise
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a smart meal planner assistant."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content