from db import query as safe_query

def update_payment_status(reference, status):
    safe_query(
        "UPDATE payments SET status=%s WHERE reference=%s",
        (status, reference)
    )