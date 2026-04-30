from db import query as safe_query

def update_user(user_id, data: dict):
    fields = ", ".join([f"{k}=%s" for k in data.keys()])
    values = list(data.values())

    safe_query(
        f"UPDATE users SET {fields} WHERE telegram_id=%s",
        (*values, str(user_id))
    )