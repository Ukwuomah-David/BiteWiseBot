from flask import Flask, request, abort
import os
import requests
import hmac
import hashlib
import datetime

from sheets import update_user, get_user

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# =========================
# PAYSTACK SUCCESS PAGE (CALLBACK)
# =========================
@app.route("/payment-success", methods=["GET"])
def payment_success():
    reference = request.args.get("reference")
    trxref = request.args.get("trxref")

    return f"""
    <h1>✅ Payment Successful</h1>
    <p>Reference: {reference}</p>
    <p>Transaction: {trxref}</p>
    <p>You can return to Telegram.</p>
    """


# =========================
# VERIFY PAYSTACK SIGNATURE
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
# SCHOOL CALENDAR LOGIC
# =========================
def is_school_active():
    month = datetime.datetime.now().month
    return month in [2, 3, 4, 5, 6, 9, 10, 11]


# =========================
# CHECK PREMIUM STATUS
# =========================
def is_already_premium(user_id):
    user = get_user(user_id)
    return user and user.get("plan") == "premium"


# =========================
# SEND TELEGRAM MESSAGE
# =========================
def send_telegram_message(chat_id, text):
    if not TELEGRAM_BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": text
    })


# =========================
# WEBHOOK ENDPOINT
# =========================
@app.route("/paystack-webhook", methods=["POST"])
def webhook():

    # 🔐 verify Paystack signature
    if not verify_signature(request):
        abort(400)

    event = request.json

    if event.get("event") == "charge.success":

        data = event.get("data", {})
        metadata = data.get("metadata", {})

        telegram_id = metadata.get("telegram_id")
        plan = metadata.get("plan", "premium")
        reference = data.get("reference")

        if not telegram_id or not reference:
            return "missing data", 200

        # 🎓 school rule
        if not is_school_active():
            return "school break - no upgrade", 200

        # 🔁 prevent duplicates
        if is_already_premium(telegram_id):
            return "already premium", 200

        # 🔍 verify transaction with Paystack
        verify = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        ).json()

        if verify.get("data", {}).get("status") == "success":

            # 💳 upgrade user
            if plan == "premium":
                update_user(telegram_id, plan="premium")

                # 🔥 send Telegram message
                send_telegram_message(
                    telegram_id,
                    "🔥 Payment confirmed. You're now Premium!"
                )

            return "upgraded", 200

    return "ignored", 200


# =========================
# RUN SERVER (Render)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)