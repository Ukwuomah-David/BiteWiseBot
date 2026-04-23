from googleapiclient.discovery import build
from google.oauth2 import service_account

# ==============================
# CONFIG
# ==============================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SPREADSHEET_ID = "1NciP7t98chVepQf8BYxmlpbLc5HXUTFH7mpvL0t5Eac"

# ==============================
# AUTH
# ==============================
import os
import json
from google.oauth2 import service_account

service_json = os.getenv("SERVICE_ACCOUNT_JSON")

if not service_json:
    raise Exception("SERVICE_ACCOUNT_JSON is missing. Check your .env or environment variables.")

service_account_info = json.loads(service_json)

creds = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)
service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()

# ==============================
# READ SHEET
# ==============================
def read_range(range_name):
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute()

    return result.get("values", [])


# ==============================
# VENDORS
# ==============================
def get_vendors():
    data = read_range("VENDORS!A2:D")
    vendors = []

    for row in data:
        if len(row) < 2:
            continue

        try:
            rating = float(row[2]) if len(row) > 2 and row[2] else 3.0
        except:
            rating = 3.0

        vendors.append({
            "vendor_id": int(row[0]),
            "vendor_name": row[1],
            "rating": rating,
            "default_meal_times": row[3] if len(row) > 3 else "ANYTIME"
        })

    return vendors


# ==============================
# MENU ITEMS
# ==============================
def get_menu_items():
    data = read_range("MENU_ITEMS!A2:E")
    items = []

    for row in data:
        if len(row) < 5:
            continue

        try:
            items.append({
                "item_id": int(row[0]),
                "vendor_id": int(row[1]),
                "vendor_name": row[2],
                "item_name": row[3],
                "price": int(row[4])
            })
        except:
            continue

    return items


# ==============================
# USERS (UPDATED FOR FSM)
# ==============================
def get_user(telegram_id):
    data = read_range("USERS!A2:G")

    for row in data:
        if len(row) < 4:
            continue

        if str(row[0]) == str(telegram_id):
            return {
                "telegram_id": str(row[0]),
                "name": row[1],
                "plan": row[2],
                "budget": int(row[3]) if row[3] else 0,
                "state": row[4] if len(row) > 4 else None,
                "allergies": row[5] if len(row) > 5 else "",
                "meals": row[6] if len(row) > 6 else ""
            }

    return None


# ==============================
# FIND USER ROW
# ==============================
def find_user_row(telegram_id):
    data = read_range("USERS!A2:G")

    for i, row in enumerate(data, start=2):
        if str(row[0]) == str(telegram_id):
            return i

    return None


# ==============================
# SAVE USER
# ==============================
def save_user(telegram_id, name, plan="free", budget=0):
    if get_user(telegram_id):
        return

    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="USERS!A:G",
        valueInputOption="USER_ENTERED",
        body={"values": [[telegram_id, name, plan, budget, "", "", ""]]}
    ).execute()


# ==============================
# UPDATE USER (FIXED FLEXIBLE)
# ==============================
def update_user(telegram_id, plan=None, budget=None, name=None, state=None, allergies=None, meals=None):
    row = find_user_row(telegram_id)

    if not row:
        return

    def update_cell(col, value):
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"USERS!{col}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]}
        ).execute()

    if name is not None:
        update_cell("B", name)

    if plan is not None:
        update_cell("C", plan)

    if budget is not None:
        update_cell("D", budget)

    if state is not None:
        update_cell("E", state)

    if allergies is not None:
        update_cell("F", allergies)

    if meals is not None:
        update_cell("G", meals)


# ==============================
# UPSERT
# ==============================
def upsert_user(telegram_id, name, plan="free", budget=0):
    user = get_user(telegram_id)

    if user:
        update_user(telegram_id, plan=plan, budget=budget, name=name)
    else:
        save_user(telegram_id, name, plan, budget)


# ==============================
# VENDOR RATING
# ==============================
def save_vendor_rating(user_id, vendor_id, rating):
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="RATINGS!A:C",
        valueInputOption="USER_ENTERED",
        body={"values": [[str(user_id), str(vendor_id), int(rating)]]}
    ).execute()