import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True

def query(sql, params=None, fetch=False):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        if fetch:
            return cur.fetchall()