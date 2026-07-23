# CRUD API

A simple in-memory task management API built with FastAPI, as part of the FlyRank AI Backend Engineering Internship.

Supports full CRUD (Create, Read, Update, Delete) on tasks, with input validation, correct HTTP status codes, consistent JSON error responses, and interactive Swagger documentation.

**Note:** Data is stored in memory only and resets whenever the server restarts. Persistent storage (SQLite) is introduced in a later assignment.

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

---

## Endpoints

| Method | Path            | Description                          | Success | Error cases           |
|--------|-----------------|---------------------------------------|---------|------------------------|
| GET    | `/`             | API info                              | 200     | —                       |
| GET    | `/health`       | Health check                          | 200     | —                       |
| GET    | `/tasks`        | List all tasks                        | 200     | —                       |
| GET    | `/tasks/{id}`   | Get a single task                     | 200     | 404 if not found        |
| POST   | `/tasks`        | Create a task                         | 201     | 400 if title missing/empty |
| PUT    | `/tasks/{id}`   | Update a task                         | 200     | 400 invalid body, 404 not found |
| DELETE | `/tasks/{id}`   | Delete a task                         | 204     | 404 if not found        |

All error responses use the shape:
```json
{"error": "Task 99 not found"}
```

---

## Example request

```powershell
curl.exe -i http://127.0.0.1:8000/tasks
```
HTTP/1.1 200 OK
content-type: application/json
[
{"id": 1, "title": "Buy groceries", "done": false},
{"id": 2, "title": "Write project report", "done": false},
{"id": 3, "title": "Walk the dog", "done": true}
]
---

## Swagger UI

![Swagger UI](swagger-ui.png)

---

## Tech stack

- Python 3.12
- FastAPI
- Uvicorn

## AI vs Me (Stage 7 — AI Rematch)

As a bonus stage, I wrote an original prompt from memory (no copying from the assignment brief) and had an AI generate the same CRUD API independently in [`ai-version/`](ai-version/). Both versions were tested against the same checkpoints and diffed.

**Concrete differences found:**

1. **No pre-seeded data** — my version pre-seeds 3 tasks on startup (required by the brief); the AI version starts with an empty list, since my prompt never mentioned seed data.
2. **Different field name** — I used `done`; the AI used `completed`. Neither is "wrong," but it shows how an unspecified schema leads to arbitrary naming choices.
3. **Missing input validation** — my version rejects empty/whitespace-only titles with `400`; the AI version has no such check at all, since my prompt didn't explicitly call out validation rules.
4. **Generic vs specific error messages** — my 404s say `"Task 4 not found"` (includes the id); the AI's say only `"Task not found"`, since I never specified the exact error message format.
5. **Default status codes** — my `POST /tasks` returns `201 Created` and `DELETE /tasks/{id}` returns `204 No Content` with no body; the AI version left both as FastAPI's default `200 OK`, including a JSON body on delete.
6. **Custom error shape** — my version enforces `{"error": "..."}` across the app via two global exception handlers; the AI version uses FastAPI's raw default (`{"detail": "..."}`).
7. **PUT semantics** — mine requires a full `title` on every update (reuses the create model); the AI made all update fields optional, allowing partial updates — a legitimate but different design decision.

**Takeaway:** Nearly every difference traces back to details my prompt left unstated — exact status codes, error shapes, seed data, and validation rules. The AI's code wasn't *wrong*, it was a reasonable interpretation of an underspecified spec. This was the clearest lesson from this stage: precision in a prompt directly determines how closely the output matches what you actually need.

**Rematch:** I rewrote the prompt to explicitly specify the field name, seed data, validation rules, exact error messages, status codes, error shape, and PUT semantics — the resulting rematch output matched my hand-built version almost exactly, confirming that most of the original gap was a prompt precision problem, not a model capability problem.