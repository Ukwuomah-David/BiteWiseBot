import time
import requests
import logging

from redis_queue import pop_payment_job
from db import query
from user_service import upgrade_user

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)


def send_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=5
    )


def process_payment(reference, telegram_id):
    try:
        # verify Paystack
        res = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            timeout=10
        ).json()

        if res.get("data", {}).get("status") != "success":
            query(
                "UPDATE payments SET status='failed' WHERE reference=%s",
                (reference,)
            )
            return

        # idempotent update
        updated = query(
            """
            UPDATE payments
            SET status='success', updated_at=NOW()
            WHERE reference=%s AND status!='success'
            """,
            (reference,)
        )

        if not updated:
            return

        upgrade_user(telegram_id)

        send_message(telegram_id, "🔥 Payment confirmed. Premium activated!")

        logging.info(f"Payment success: {reference}")

    except Exception as e:
        logging.error(f"Worker error: {e}")


def worker_loop():
    while True:
        job = pop_payment_job()

        if not job:
            time.sleep(1)
            continue

        reference, telegram_id = job
        process_payment(reference, telegram_id)


if __name__ == "__main__":
    worker_loop()