from flask import Flask, request, abort
import os
import hmac
import hashlib
import requests
import logging
from datetime import datetime

from db import query
from user_service import upgrade_user

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")



# =========================
# LOGGING (IMPORTANT FOR PROD)
# =========================
logging.basicConfig(level=logging.INFO)


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
# TELEGRAM SENDER (SAFE)
# =========================
def send_message(chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5
        )
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")


# =========================
# ATOMIC PAYMENT LOCK
# =========================
def lock_payment(reference):
    return query(
        """
        UPDATE payments
        SET status = 'processing'
        WHERE reference = %s
          AND status = 'pending'
        RETURNING telegram_id
        """,
        (reference,),
        fetch=True
    )



# =========================
# WEBHOOK
# =========================
@app.route("/paystack-webhook", methods=["POST"])
def webhook():
    try:
        # =========================
        # SECURITY CHECK
        # =========================
        if not verify_signature(request):
            logging.warning("Invalid Paystack signature")
            return "invalid signature", 400

        event = request.json or {}

        if event.get("event") != "charge.success":
            return "ignored", 200

        data = event.get("data", {})
        reference = data.get("reference")

        if not reference:
            return "missing reference", 200

        # =========================
        # STEP 1: LOCK PAYMENT (CRITICAL)
        # =========================
        locked = lock_payment(reference)

        if not locked:
            logging.info(f"Duplicate or invalid webhook: {reference}")
            return "ignored", 200

        telegram_id = locked[0][0]

        # =========================
        # STEP 2: VERIFY WITH PAYSTACK
        # =========================
        verify = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"},
            timeout=10
        )

        if verify.status_code != 200:
            logging.error(f"Paystack verify failed: {reference}")
            return "verify failed", 200

        verify = verify.json()

        if not verify.get("data") or verify["data"].get("status") != "success":
            # rollback payment status
            query(
                "UPDATE payments SET status='failed' WHERE reference=%s",
                (reference,)
            )
            return "payment not successful", 200

        # =========================
        # STEP 3: FINALIZE PAYMENT
        # =========================
        query(
            """
            UPDATE payments
            SET status='success',
                updated_at = NOW()
            WHERE reference=%s
            """,
            (reference,)
        )

        # =========================
        # STEP 4: UPGRADE USER
        # =========================
        try:
            upgrade_user(telegram_id)
        except Exception as e:
            logging.error(f"Upgrade failed: {e}")

        # =========================
        # STEP 5: NOTIFY USER
        # =========================
        send_message(
            telegram_id,
            "🔥 Payment confirmed. You're now Premium!"
        )

        logging.info(f"Payment success: {reference} -> {telegram_id}")

        return "ok", 200

    except Exception as e:
        logging.error(f"Webhook error: {str(e)}")
        return "internal error", 200


# =========================
# HEALTH CHECK
# =========================
@app.route("/")
def home():
    return "Webhook is live 🚀", 200


# =========================
# RUN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)