# =========================
# APP.PY (BOT + WEBHOOK MERGED CLEANLY)
# =========================

import os
import hmac
import hashlib
import logging
import requests
import asyncio

from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# 🔥 IMPORT YOUR EXISTING LOGIC
from bot import start, button_handler, handle_message, menu_command
from db import query
from schedule_worker import generate_and_send
from user_service import upgrade_user

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET")

logging.basicConfig(level=logging.INFO)

# =========================
# TELEGRAM BOT SETUP
# =========================
telegram_app = Application.builder().token(BOT_TOKEN).build()

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("menu", menu_command))
telegram_app.add_handler(CallbackQueryHandler(button_handler))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# =========================
# FASTAPI SETUP
# =========================
app = FastAPI()


# =========================
# TELEGRAM SENDER
# =========================
async def send_telegram_message(user_id, text):
    try:
        await telegram_app.bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logging.error(f"Telegram send error: {e}")


# =========================
# VERIFY PAYSTACK SIGNATURE
# =========================
def verify_signature(req_body, signature):
    if not signature or not PAYSTACK_SECRET:
        return False

    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        req_body,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(signature, computed)


# =========================
# PAYSTACK WEBHOOK
# =========================
@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):

    body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = await request.json()

    if event.get("event") != "charge.success":
        return {"status": "ignored"}

    data = event.get("data", {})
    reference = data.get("reference")

    if not reference:
        return {"status": "no reference"}

    # =========================
    # FIND USER
    # =========================
    rows = query(
        "SELECT telegram_id FROM payments WHERE reference=%s",
        (reference,),
        fetch=True
    )

    if not rows:
        return {"status": "unknown reference"}

    telegram_id = rows[0][0]

    # =========================
    # UPDATE PAYMENT
    # =========================
    query(
        """
        UPDATE payments
        SET status='success', updated_at=NOW()
        WHERE reference=%s AND status!='success'
        """,
        (reference,)
    )

    # =========================
    # UPGRADE USER
    # =========================
    upgrade_user(telegram_id)

    # =========================
    # SEND MESSAGE
    # =========================
    await send_telegram_message(
        telegram_id,
        "🎉 Payment successful! Premium activated."
    )

    logging.info(f"Payment success for {telegram_id}")

    return {"status": "ok"}


# =========================
# DAILY MEALS ENDPOINT
# =========================
@app.post("/run-daily")
async def run_daily():
    generate_and_send()
    return {"status": "sent"}


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
def home():
    return {"status": "running"}


# =========================
# START EVERYTHING CLEANLY
# =========================
async def main():
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()

    logging.info("Bot started...")

    # keep running forever
    while True:
        await asyncio.sleep(3600)


# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    import uvicorn

    loop = asyncio.get_event_loop()

    loop.create_task(main())

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))