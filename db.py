import os
import psycopg2
import logging
import time


import time
import logging

def safe_query(sql, params=None, fetch=False, retries=3):
    for i in range(retries):
        try:
            return query(sql, params, fetch=fetch)
        except Exception as e:
            logging.error(f"DB ERROR attempt {i+1}: {e}")
            time.sleep(0.5)

    logging.critical("DB FAILED AFTER RETRIES")
    return None if fetch else False
DATABASE_URL = os.getenv("DATABASE_URL")


# =========================
# CONNECTION
# =========================
def get_connection():
    try:
        return psycopg2.connect(
            DATABASE_URL,
            sslmode="require",
            connect_timeout=5
        )
    except Exception as e:
        logging.error(f"DB connection failed: {e}")
        raise


# =========================
# QUERY EXECUTOR
# =========================
def query(sql, params=None, fetch=False, retries=2):

    for attempt in range(retries + 1):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(sql, params or ())

            result = cur.fetchall() if fetch else None

            conn.commit()
            cur.close()
            conn.close()

            return result

        except psycopg2.OperationalError as e:
            logging.warning(f"DB retry {attempt + 1}: {e}")
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"DB query error: {e}")
            if conn:
                conn.rollback()
                conn.close()
            return None

    logging.error("DB failed after retries")
    return None
print("DB URL:", DATABASE_URL)