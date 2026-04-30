from fsm_engine import run_fsm, set_state, can_transition

async def handle_fsm(update, context, user_id, data):
    next_state = can_transition(user_id, data)

    if next_state:
        set_state(user_id, next_state)

    return await run_fsm(update, context)