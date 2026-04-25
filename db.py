import os
import psycopg2
import psycopg2.extras
import logging
import time

DATABASE_URL = os.getenv("DATABASE_URL")

# =========================
# CONNECTION (LAZY + SAFE)
# =========================
def get_connection():
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode="require",
            connect_timeout=5
        )
        return conn
    except Exception as e:
        logging.error(f"DB connection failed: {e}")
        raise


# =========================
# QUERY EXECUTOR (PROD SAFE)
# =========================
def query(sql, params=None, fetch=False, retries=2):
    """
    Universal DB query function
    - Auto retry (important for Supabase pooler)
    - Safe commit handling
    - Fetch support
    """

    for attempt in range(retries + 1):
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute(sql, params or ())

            if fetch:
                result = cur.fetchall()
            else:
                result = None

            conn.commit()
            cur.close()
            conn.close()

            return result

        except psycopg2.OperationalError as e:
            logging.warning(f"DB retry {attempt+1}: {e}")
            time.sleep(0.5)

        except Exception as e:
            logging.error(f"DB query error: {e}")
            if conn:
                conn.rollback()
                conn.close()
            return None

    logging.error("DB failed after retries")
    return None
import redis
import os

redis_conn = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)