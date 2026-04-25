import redis
import json
import os

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

QUEUE_KEY = "payments_queue"
DLQ_KEY = "payments_dead_letter"
def push_payment_job(reference, telegram_id):
    job = {
        "reference": reference,
        "telegram_id": telegram_id,
        "attempts": 0
    }

    r.lpush(QUEUE_KEY, json.dumps(job))

job = pop_payment_job()
    data = r.brpop(QUEUE_KEY, timeout=10)
    if not data:
        return None

    return json.loads(data[1])
def move_to_dead_letter(job):
    r.lpush(DLQ_KEY, json.dumps(job))
