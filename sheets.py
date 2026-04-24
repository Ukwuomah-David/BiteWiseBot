from db import query


# =========================
# MENU ITEMS
# =========================
def get_menu_items():
    rows = query("""
        SELECT 
            m.item_id,
            v.vendor_name,
            m.item_name,
            m.price
        FROM menu_items m
        JOIN vendors v ON m.vendor_id = v.vendor_id
    """, fetch=True)

    return [
        {
            "item_id": r[0],
            "vendor_name": r[1],
            "item_name": r[2],
            "price": r[3]
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

def get_vendor_scores():
    rows = query("""
        SELECT vendor_name, AVG(rating)
        FROM ratings
        GROUP BY vendor_name
    """, fetch=True)

    return {r[0]: float(r[1]) for r in rows} if rows else {}

    
def get_user_vendor_scores(user_id):
    rows = query("""
        SELECT vendor_name, AVG(rating)
        FROM ratings
        WHERE telegram_id=%s
        GROUP BY vendor_name
    """, (str(user_id),), fetch=True)

    return {r[0]: float(r[1]) for r in rows} if rows else {}