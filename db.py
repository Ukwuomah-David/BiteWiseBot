import psycopg2
from psycopg2.pool import SimpleConnectionPool
import os

DATABASE_URL = os.getenv("DATABASE_URL")

pool = SimpleConnectionPool(
    1, 20,  # min, max connections
    DATABASE_URL
)

def query(sql, params=None, fetch=False):
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())

        if fetch:
            result = cur.fetchall()
        else:
            result = None

        conn.commit()
        cur.close()
        return result
    finally:
        pool.putconn(conn)