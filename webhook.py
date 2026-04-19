from flask import Flask, request
import requests
import os
from sheets import update_user

app = Flask(__name__)

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")

@app.route("/paystack-webhook", methods=["POST"])
def paystack_webhook():
    data = request.json

    event = data.get("event")

    if event == "charge.success":
        payload = data["data"]

        reference = payload["reference"]
        metadata = payload.get("metadata", {})
        telegram_id = metadata.get("telegram_id")

        # VERIFY PAYMENT (IMPORTANT SECURITY STEP)
        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET}"
        }

        verify = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers
        ).json()

        if verify["data"]["status"] == "success":
            update_user(telegram_id, plan="premium")

    return "OK", 200


if __name__ == "__main__":
    app.run(port=5000)