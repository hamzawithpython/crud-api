from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from contextlib import asynccontextmanager
from database import init_db, get_connection, row_to_task


class TaskCreate(BaseModel):
    title: str
    done: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()   # runs once when the server starts
    yield       # server is now running and handling requests

app = FastAPI(
    title="CRUD API",
    description="A simple task management API built for the FlyRank AI Backend Engineering Internship.",
    version="0.2.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0]
    field = first_error["loc"][-1]
    return JSONResponse(status_code=400, content={"error": f"{field} is required"})



@app.get("/", summary="API info", description="Returns basic information about this API.")
def root():
    return {
        "name": "CRUD API",
        "description": "A simple in-memory task management API",
        "version": "0.1.0",
    }


@app.get("/health", summary="Health check", description="Returns a simple status indicating the server is running.")
def health():
    return {"status": "ok"}


@app.get("/tasks", summary="List all tasks", description="Returns the full list of tasks currently in memory.")
def get_tasks():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return [row_to_task(row) for row in rows]


@app.get("/tasks/{task_id}", summary="Get a single task", description="Returns one task by its id, or 404 if it doesn't exist.")
def get_task(task_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return row_to_task(row)


@app.post(
    "/tasks",
    status_code=201,
    summary="Create a task",
    description="Creates a new task with an auto-assigned id. Title is required and cannot be empty.",
)
def create_task(task: TaskCreate):
    if not task.title or not task.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (task.title, int(task.done)),
    )
    conn.commit()
    new_id = cursor.lastrowid
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return row_to_task(row)


@app.put(
    "/tasks/{task_id}",
    summary="Update a task",
    description="Replaces an existing task's title and done status. Returns 404 if the task doesn't exist.",
)
def update_task(task_id: int, task: TaskCreate):
    if not task.title or not task.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    for existing in tasks:
        if existing["id"] == task_id:
            existing["title"] = task.title
            existing["done"] = task.done
            return existing

    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    summary="Delete a task",
    description="Deletes a task by its id. Returns 404 if the task doesn't exist.",
)
def delete_task(task_id: int):
    for existing in tasks:
        if existing["id"] == task_id:
            tasks.remove(existing)
            return

    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")