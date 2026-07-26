import os
import psycopg


def get_connection():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def row_to_task(row, cursor):
    """Convert a raw psycopg row tuple to a dict using cursor column names."""
    cols = [desc[0] for desc in cursor.description]
    d = dict(zip(cols, row))
    d["done"] = bool(d["done"])
    return d


def init_db():
    """Create the tasks table and seed it — runs once on server startup."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id    SERIAL PRIMARY KEY,
            title TEXT   NOT NULL,
            done  BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    # Seeding guard
    cur.execute("SELECT COUNT(*) FROM tasks")
    count = cur.fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO tasks (title, done) VALUES (%s, %s)",
            [
                ("Buy groceries", False),
                ("Write project report", False),
                ("Walk the dog", True),
            ],
        )

    cur.close()
    conn.close()