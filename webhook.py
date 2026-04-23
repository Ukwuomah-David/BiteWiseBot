from flask import Flask, request, abort
import os, hmac, hashlib, requests

from db import query
from user_service import upgrade_user

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")


def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")

    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(signature, computed)


def send_message(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )


@app.route("/paystack-webhook", methods=["POST"])
def webhook():

    if not verify_signature(request):
        abort(400)

    event = request.json

    if event.get("event") != "charge.success":
        return "ignored", 200

    data = event["data"]
    reference = data["reference"]

    # 🔥 CHECK PAYMENT EXISTS
    rows = query(
        "SELECT telegram_id, status FROM payments WHERE reference=%s",
        (reference,),
        fetch=True
    )

    if not rows:
        return "unknown reference", 200

    telegram_id, status = rows[0]

    # 🔥 IDEMPOTENCY (CRITICAL)
    if status == "success":
        return "already processed", 200

    # 🔥 VERIFY FROM PAYSTACK
    verify = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
    ).json()

    if verify["data"]["status"] != "success":
        return "not successful", 200

    # 🔥 MARK SUCCESS
    query(
        "UPDATE payments SET status='success' WHERE reference=%s",
        (reference,)
    )

    # 🔥 UPGRADE USER
    upgrade_user(telegram_id)

    send_message(
        telegram_id,
        "🔥 Payment confirmed. You're now Premium!"
    )

    return "ok", 200


if __name__ == "__main__":
    app.run(port=10000)