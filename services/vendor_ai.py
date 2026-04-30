from db import query as safe_query

def rate_vendor(user_id, vendor, rating, meal):
    safe_query(
        "INSERT INTO vendor_ratings (user_id, vendor, rating, meal) VALUES (%s,%s,%s,%s)",
        (user_id, vendor, rating, meal)
    )


def get_best_vendors(meal):
    rows = safe_query(
        "SELECT vendor, AVG(rating) as avg_rating FROM vendor_ratings WHERE meal=%s GROUP BY vendor ORDER BY avg_rating DESC",
        (meal,),
        fetch=True
    )

    return [r[0] for r in rows] if rows else []