from flask import Flask, request, abort
import os
import requests
import hmac
import hashlib
import datetime

from user_service import upgrade_user, is_premium

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# =========================
# SUCCESS PAGE
# =========================
@app.route("/payment-success")
def payment_success():
    return """
    <h1>✅ Payment Successful</h1>
    <p>You can return to Telegram.</p>
    """

# =========================
# VERIFY SIGNATURE
# =========================
def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")

    if not signature:
        return False

    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(signature, computed)


# =========================
# SCHOOL RULE
# =========================
def is_school_active():
    month = datetime.datetime.now().month
    return month in [2, 3, 4, 5, 6, 9, 10, 11]


# =========================
# TELEGRAM MESSAGE
# =========================
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })


# =========================
# WEBHOOK
# =========================
@app.route("/paystack-webhook", methods=["POST"])
def webhook():

    if not verify_signature(request):
        abort(400)

    event = request.json

    if event.get("event") == "charge.success":

        data = event.get("data", {})
        metadata = data.get("metadata", {})

        telegram_id = metadata.get("telegram_id")
        reference = data.get("reference")

        if not telegram_id or not reference:
            return "missing data", 200

        if not is_school_active():
            return "school break", 200

        if is_premium(telegram_id):
            return "already premium", 200

        verify = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        ).json()

        if verify.get("data", {}).get("status") == "success":

            upgrade_user(telegram_id)

            send_telegram_message(
                telegram_id,
                "🔥 Payment confirmed. You're now Premium!"
            )

            return "upgraded", 200

    return "ignored", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)