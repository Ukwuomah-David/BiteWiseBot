from flask import Flask, request, abort
import os
import hmac
import hashlib
import requests
import logging

from db import query
from redis_queue import push_payment_job



PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

# =========================

# TELEGRAM SENDER

# =========================

def send_telegram_message(user_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    
    try:
        res = requests.post(
            url,
            json={
                "chat_id": user_id,
                "text": text,
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "🍽 Open Menu", "callback_data": "menu"}
                        ]
                    ]
                }
            },
            timeout=10
        )

        if res.status_code != 200:
            logging.error(f"Telegram API error: {res.text}")

    except Exception as e:
        logging.error(f"Telegram send error: {e}")
    

# =========================

# VERIFY PAYSTACK SIGNATURE

# =========================

def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")

    if not signature or not PAYSTACK_SECRET:
        return False

    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(signature, computed)
```

# =========================

# OPTIONAL: VERIFY WITH PAYSTACK API (EXTRA SECURITY)

# =========================

def verify_transaction(reference):
try:
res = requests.get(
f"https://api.paystack.co/transaction/verify/{reference}",
headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"},
timeout=10
)
return res.json()
except Exception as e:
logging.error(f"Verify API error: {e}")
return None

# =========================

# WEBHOOK ENDPOINT

# =========================

def webhook():
try:
# 🔒 Signature check
if not verify_signature(request):
logging.warning("Invalid signature")
return "invalid signature", 400

```
    event = request.json or {}

    # Only process successful payments
    if event.get("event") != "charge.success":
        return "ignored", 200

    data = event.get("data", {})
    reference = data.get("reference")

    if not reference:
        return "missing reference", 200

    # =========================
    # VERIFY WITH PAYSTACK (ANTI-FRAUD)
    # =========================
    verify = verify_transaction(reference)

    if not verify or not verify.get("status"):
        logging.warning(f"Verification failed for {reference}")
        return "verification failed", 400

    payment_data = verify.get("data", {})

    if payment_data.get("status") != "success":
        return "not successful", 200

    # =========================
    # DB LOOKUP
    # =========================
    rows = query(
        "SELECT telegram_id, status FROM payments WHERE reference=%s",
        (reference,),
        fetch=True
    )

    if not rows:
        return "unknown reference", 200

    telegram_id, status = rows[0]

    # =========================
    # IDEMPOTENCY (PREVENT DOUBLE CREDIT)
    # =========================
    if status == "success":
        logging.info(f"Duplicate webhook ignored: {reference}")
        return "already processed", 200

    # =========================
    # UPDATE PAYMENT STATUS
    # =========================
    query(
        """
        UPDATE payments
        SET status='success', updated_at=NOW()
        WHERE reference=%s
        """,
        (reference,)
    )

    
    # =========================
    # ACTIVATE USER
    # =========================
    from user_service import upgrade_user
    upgrade_user(telegram_id)

    # =========================
    # SEND TELEGRAM MESSAGE INSTANTLY
    # =========================
    send_telegram_message(
        telegram_id,
        "🎉 Payment successful!\n\n🔥 Your Premium access is now active."
    )

    # =========================
    # OPTIONAL: still push to worker (backup/logging)
    # =========================
    push_payment_job(reference, telegram_id)

    return "success", 200

except Exception as e:
    logging.error(f"Webhook error: {e}")
    return "internal error", 200
```
