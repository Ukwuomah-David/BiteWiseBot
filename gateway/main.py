from fastapi import FastAPI, Request
from events.dispatcher import handle_event

app = FastAPI()

@app.post("/telegram/webhook")
async def telegram_webhook(req: Request):
    update = await req.json()
    return await handle_event(update)


@app.post("/paystack/webhook")
async def paystack_webhook(req: Request):
    data = await req.json()
    return await handle_event({"type": "payment", "data": data})