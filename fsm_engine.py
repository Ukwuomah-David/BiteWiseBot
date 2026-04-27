import logging
from db import query as safe_query

FSM = {}
TRANSITIONS = {}

def state(name):
    def decorator(fn):
        FSM[name] = fn
        return fn
    return decorator


def add_transition(from_state, event, to_state, guard=None):
    TRANSITIONS.setdefault(from_state, {})
    TRANSITIONS[from_state][event] = {
        "to": to_state,
        "guard": guard
    }


def get_state(user_id):
    res = safe_query(
        "SELECT state FROM users WHERE telegram_id=%s",
        (str(user_id),),
        fetch=True
    )
    return res[0][0] if res else None


def set_state(user_id, state):
    safe_query(
        "UPDATE users SET state=%s, updated_at=NOW() WHERE telegram_id=%s",
        (state, str(user_id))
    )


def can_transition(user_id, event):
    state = get_state(user_id)

    if state not in TRANSITIONS:
        return None

    t = TRANSITIONS[state].get(event)

    if not t:
        return None

    guard = t.get("guard")

    if guard and not guard(user_id):
        return None

    return t["to"]


async def run_fsm(update, context):
    from bot import get_user_id

    user_id = get_user_id(update)
    current_state = get_state(user_id)

    if not current_state:
        set_state(user_id, "TITHE")
        current_state = "TITHE"

    handler = FSM.get(current_state)

    if not handler:
        logging.error(f"Missing handler: {current_state}")
        set_state(user_id, "TITHE")
        handler = FSM.get("TITHE")

    return await handler(update, context)