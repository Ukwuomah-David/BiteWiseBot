from flask import Flask, request, abort
import os
import requests
import hmac
import hashlib
import datetime

from sheets import update_user, get_user

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")


# =========================
# VERIFY PAYSTACK SIGNATURE
# =========================
def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")

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
    # Adjust based on your school calendar
    month = datetime.datetime.now().month

    # Active months (example: Covenant-style semesters)
    return month in [2, 3, 4, 5, 6, 9, 10, 11]


# =========================
# DUPLICATE PROTECTION
# =========================
def is_already_premium(user_id):
    user = get_user(user_id)
    return user and user.get("plan") == "premium"


# =========================
# WEBHOOK ENDPOINT
# =========================
@app.route("/paystack-webhook", methods=["POST"])
def webhook():

    # 🔐 Step 1: Verify request came from Paystack
    if not verify_signature(request):
        abort(400)

    event = request.json

    # Only care about successful payments
    if event.get("event") == "charge.success":

        data = event.get("data", {})
        metadata = data.get("metadata", {})

        telegram_id = metadata.get("telegram_id")
        plan = metadata.get("plan", "premium")
        reference = data.get("reference")

        if not telegram_id or not reference:
            return "missing data", 200

        # 🎓 Step 2: Respect school calendar (no billing during break)
        if not is_school_active():
            return "school break - no upgrade", 200

        # 🔁 Step 3: Prevent duplicate upgrades
        if is_already_premium(telegram_id):
            return "already premium", 200

        # 🔍 Step 4: VERIFY with Paystack (CRITICAL SECURITY STEP)
        verify = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        ).json()

        if verify.get("data", {}).get("status") == "success":

            # 💳 Step 5: Upgrade user
            if plan == "premium":
                update_user(telegram_id, plan="premium")

            return "upgraded", 200

    return "ignored", 200
@app.route("/payment-success", methods=["GET"])
def payment_success():
    return """
    <h2>✅ Payment Successful!</h2>
    <p>You can now return to Telegram and continue using BiteWise.</p>
    """

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)