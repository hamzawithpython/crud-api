# CRUD API

A task management API built with FastAPI and SQLite, as part of the FlyRank AI Backend Engineering Internship.

Supports full CRUD (Create, Read, Update, Delete) on tasks, with input validation, correct HTTP status codes, consistent JSON error responses, and interactive Swagger documentation.

Data is persisted to a local SQLite database (`tasks.db`) and survives server restarts.

---

## Running the project

Clone the repo, then from the project root:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive Swagger docs are available at `http://127.0.0.1:8000/docs`.

On first run, `tasks.db` is created automatically and seeded with 3 example tasks. The database file is git-ignored — every fresh clone starts with a clean database.

---

## Endpoints

| Method | Path | Description | Success | Error cases |
|--------|------|-------------|---------|-------------|
| GET | `/` | API info | 200 | — |
| GET | `/health` | Health check | 200 | — |
| GET | `/tasks` | List all tasks | 200 | — |
| GET | `/tasks/{id}` | Get a single task | 200 | 404 if not found |
| POST | `/tasks` | Create a task | 201 | 400 if title missing/empty |
| PUT | `/tasks/{id}` | Update a task | 200 | 400 invalid body, 404 not found |
| DELETE | `/tasks/{id}` | Delete a task | 204 | 404 if not found |

All error responses use the shape:
```json
{"error": "Task 99 not found"}
```

---

## Database

**Why SQLite?**  
SQLite is a zero-install, single-file database built into Python's standard library. It's the right choice for a project at this scale — no server to run, no credentials to manage, and the entire database is one file you can inspect directly. When a project grows to need concurrent writes or multiple services sharing data, that's when you'd migrate to Postgres.

**Database file:** `tasks.db` — auto-created in the project root on first run. Listed in `.gitignore` so each clone starts fresh.

**Schema:**
```sql
CREATE TABLE tasks (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT    NOT NULL,
    done  INTEGER NOT NULL DEFAULT 0
);
```

**Example queries (run directly against the DB):**
```powershell
# All tasks
python -c "import sqlite3; conn = sqlite3.connect('tasks.db'); [print(tuple(r)) for r in conn.execute('SELECT * FROM tasks')]"

# Completed tasks only
python -c "import sqlite3; conn = sqlite3.connect('tasks.db'); [print(tuple(r)) for r in conn.execute('SELECT * FROM tasks WHERE done = 1')]"
```

---

## Example requests

```powershell
# List all tasks
curl.exe http://127.0.0.1:8000/tasks

# Get one task
curl.exe http://127.0.0.1:8000/tasks/1

# Create a task
curl.exe -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d '{\"title\": \"Read a book\", \"done\": false}'

# Update a task
curl.exe -X PUT http://127.0.0.1:8000/tasks/1 -H "Content-Type: application/json" -d '{\"title\": \"Buy groceries and cook\", \"done\": true}'

# Delete a task
curl.exe -X DELETE http://127.0.0.1:8000/tasks/4
```

---

## Tech stack

- Python 3.12
- FastAPI
- Uvicorn
- SQLite (via Python stdlib `sqlite3`)

---

## AI vs Me (Stage 6 — AI Rematch)

*(Carried over from A1)* An AI-generated version of this API is in [`ai-version/`](ai-version/). See the A1 rematch notes for the full diff and takeaways.