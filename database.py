import sqlite3

DB_PATH = "tasks.db"


def get_connection():
    """Open and return a connection to the SQLite database.
    
    row_factory = sqlite3.Row makes rows behave like dicts:
    you can access columns by name (row["title"]) instead of index (row[1]).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_task(row):
    """Convert a sqlite3.Row to a plain dict with a proper Python bool for 'done'.
    
    SQLite stores done as INTEGER (0 or 1). JSON needs true/false.
    dict(row) gives {"id": 1, "title": "...", "done": 0} — wrong type.
    bool(0) = False, bool(1) = True — correct.
    """
    d = dict(row)
    d["done"] = bool(d["done"])
    return d


def init_db():
    """Create the tasks table and seed it — runs once on server startup.
    
    CREATE TABLE IF NOT EXISTS means this is safe to call every restart:
    it only creates the table when it doesn't exist yet.
    
    The seeding guard (COUNT check) ensures the 3 example tasks are
    inserted exactly once — never duplicated on subsequent restarts.
    """
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Seeding guard — only insert if the table is empty
    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            [
                ("Buy groceries", 0),
                ("Write project report", 0),
                ("Walk the dog", 1),
            ],
        )

    conn.commit()
    conn.close()