import psycopg2
import os

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()


def query(sql, params=None, fetch=False):
    cursor.execute(sql, params or ())
    conn.commit()

    if fetch:
        return cursor.fetchall()