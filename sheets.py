from db import query


# =========================
# MENU ITEMS
# =========================
def get_menu_items():
    rows = query("SELECT vendor_name, item_name, price FROM menu_items", fetch=True)

    return [
        {
            "vendor_name": r[0],
            "item_name": r[1],
            "price": r[2]
        }
        for r in rows
    ]


# =========================
# USERS
# =========================
def get_user(telegram_id):
    rows = query(
        "SELECT telegram_id, name, plan, budget, state, allergies, meals, premium_expiry FROM users WHERE telegram_id=%s",
        (str(telegram_id),),
        fetch=True
    )

    if not rows:
        return None

    r = rows[0]

    return {
        "telegram_id": r[0],
        "name": r[1],
        "plan": r[2],
        "budget": r[3],
        "state": r[4],
        "allergies": r[5] or "",
        "meals": r[6] or "",
        "premium_expiry": r[7]
    }


def save_user(telegram_id, name, plan="free", budget=0):
    query(
        """
        INSERT INTO users (telegram_id, name, plan, budget)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO NOTHING
        """,
        (str(telegram_id), name, plan, budget)
    )


def update_user(
    telegram_id,
    name=None,
    plan=None,
    budget=None,
    state=None,
    allergies=None,
    meals=None,
    premium_expiry=None
):
    fields = []
    values = []

    def add(field, value):
        fields.append(f"{field}=%s")
        values.append(value)

    if name is not None: add("name", name)
    if plan is not None: add("plan", plan)
    if budget is not None: add("budget", budget)
    if state is not None: add("state", state)
    if allergies is not None: add("allergies", allergies)
    if meals is not None: add("meals", meals)
    if premium_expiry is not None: add("premium_expiry", premium_expiry)

    if not fields:
        return

    values.append(str(telegram_id))

    query(
        f"UPDATE users SET {', '.join(fields)} WHERE telegram_id=%s",
        values
    )


# =========================
# RATINGS
# =========================
def save_vendor_rating(user_id, vendor, rating):
    query(
        "INSERT INTO ratings (telegram_id, vendor_name, rating) VALUES (%s,%s,%s)",
        (str(user_id), vendor, rating)
    )