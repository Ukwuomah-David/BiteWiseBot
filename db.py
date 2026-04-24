import psycopg2
from psycopg2 import pool
import os

DATABASE_URL = os.getenv("DATABASE_URL")

connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20, DATABASE_URL
)

def query(sql, params=None, fetch=False):
    conn = connection_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)

        if fetch:
            result = cur.fetchall()
        else:
            result = None

        conn.commit()
        cur.close()
        return result

    finally:
        connection_pool.putconn(conn)