`.env` is git-ignored and never committed. `.env.example` is the reference for anyone cloning this repo.

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

## Example request

```powershell
curl.exe -i http://127.0.0.1:8080/tasks
```

HTTP/1.1 200 OK
content-type: application/json

[
{"id": 1, "title": "Buy groceries", "done": false},
{"id": 2, "title": "Write project report", "done": false},
{"id": 3, "title": "Walk the dog", "done": true}
]

---

## Database

**Why PostgreSQL?**  
SQLite (A2) is a single-file database — great for local development, but limited to one writer at a time and not suitable for multi-service production deployments. PostgreSQL is a full client-server database that handles concurrent connections, has a real boolean type, and is the standard choice for production FastAPI apps. Running it in Docker means zero local installation required.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS tasks (
    id    SERIAL PRIMARY KEY,
    title TEXT   NOT NULL,
    done  BOOLEAN NOT NULL DEFAULT FALSE
);
```

**Persistence:** Data lives in a named Docker volume (`tasks-db-data`). Running `docker compose down && docker compose up` preserves all data. Only `docker compose down -v` removes it.

---

## Tech stack

- Python 3.12
- FastAPI
- Uvicorn
- PostgreSQL 16 (via Docker)
- psycopg 3
- Docker Compose