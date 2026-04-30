import redis
import os

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    decode_responses=True
)

# FSM STATE
def set_state(user_id, state):
    r.set(f"state:{user_id}", state)

def get_state(user_id):
    return r.get(f"state:{user_id}")


# SESSION CACHE
def cache_meal(user_id, meal_data):
    r.setex(f"meal:{user_id}", 3600, str(meal_data))