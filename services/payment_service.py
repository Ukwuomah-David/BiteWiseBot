import uuid
import requests
import os
from db import query as safe_query
from repositories.payment_repo import update_payment_status

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")


class PaymentService:

    def create_payment(self, user_id, amount=100000):
        reference = str(uuid.uuid4())

        safe_query(
            "INSERT INTO payments (reference, telegram_id, amount, status) VALUES (%s,%s,%s,%s)",
            (reference, str(user_id), amount, "pending")
        )

        res = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json={
                "email": f"{user_id}@bitewise.bot",
                "amount": amount,
                "reference": reference,
                "metadata": {"telegram_id": str(user_id)}
            },
            headers={
                "Authorization": f"Bearer {PAYSTACK_SECRET}",
                "Content-Type": "application/json"
            }
        )

        return res.json().get("data", {}).get("authorization_url")


    def verify_payment(self, reference):
        # called by webhook worker
        update_payment_status(reference, "success")
        return True