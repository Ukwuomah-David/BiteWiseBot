from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
import json

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SPREADSHEET_ID = "1NciP7t98chVepQf8BYxmlpbLc5HXUTFH7mpvL0t5Eac"

service_json = os.getenv("SERVICE_ACCOUNT_JSON")

if not service_json:
    raise Exception("SERVICE_ACCOUNT_JSON is missing.")

service_account_info = json.loads(service_json)

creds = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=SCOPES
)

service = build("sheets", "v4", credentials=creds)
sheet = service.spreadsheets()


def read_range(range_name):
    return sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=range_name
    ).execute().get("values", [])


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


def get_user(telegram_id):
    data = read_range("USERS!A2:H")

    for row in data:
        if str(row[0]) == str(telegram_id):
            return {
                "telegram_id": str(row[0]),
                "name": row[1],
                "plan": row[2],
                "budget": int(row[3]) if row[3] else 0,
                "state": row[4] if len(row) > 4 else "",
                "allergies": row[5] if len(row) > 5 else "",
                "meals": row[6] if len(row) > 6 else "",
                "premium_expiry": row[7] if len(row) > 7 else ""
            }

    return None


def find_user_row(telegram_id):
    data = read_range("USERS!A2:H")

    for i, row in enumerate(data, start=2):
        if str(row[0]) == str(telegram_id):
            return i

    return None


def save_user(telegram_id, name, plan="free", budget=0):
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="USERS!A:H",
        valueInputOption="USER_ENTERED",
        body={"values": [[telegram_id, name, plan, budget, "", "", "", ""]]}
    ).execute()


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
    row = find_user_row(telegram_id)
    if not row:
        return

    def u(col, val):
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"USERS!{col}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[val]]}
        ).execute()

    if name is not None: u("B", name)
    if plan is not None: u("C", plan)
    if budget is not None: u("D", budget)
    if state is not None: u("E", state)
    if allergies is not None: u("F", allergies)
    if meals is not None: u("G", meals)
    if premium_expiry is not None: u("H", premium_expiry)


def save_vendor_rating(user_id, vendor_id, rating):
    sheet.values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="RATINGS!A:C",
        valueInputOption="USER_ENTERED",
        body={"values": [[str(user_id), str(vendor_id), int(rating)]]}
    ).execute()