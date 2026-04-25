import requests
import os
import logging
from datetime import datetime
from db import query
from user_service import build_daily_meal_message

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)


def send_message(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10
        )
    except Exception as e:
        logging.error(f"Telegram error: {e}")


def send_daily_meals():
    users = query(
        "SELECT telegram_id, name FROM users",
        fetch=True
    )

    today = datetime.utcnow().date()

    for user_id, name in users:
        try:
            # ✅ prevent duplicate sends
            exists = query(
                "SELECT 1 FROM daily_meals WHERE telegram_id=%s AND date=%s",
                (user_id, today),
                fetch=True
            )

            if exists:
                continue

            # ✅ build full message (meals + tip)
            final_message = build_daily_meal_message(user_id)

            if not final_message:
                continue

            # ✅ save to DB
            query(
                "INSERT INTO daily_meals (telegram_id, date, message) VALUES (%s,%s,%s)",
                (user_id, today, final_message)
            )

            # ✅ send to Telegram
            send_message(user_id, final_message)

            logging.info(f"Sent meal to {user_id}")

        except Exception as e:
            logging.error(f"Error for user {user_id}: {e}")