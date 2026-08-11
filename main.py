from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from contextlib import asynccontextmanager
from database import init_db, get_connection, row_to_task
from dotenv import load_dotenv
import os
from supabase import create_client, Client
from src.routes.enrich import router as enrich_router


load_dotenv()

supabase_url: str = os.environ.get("SUPABASE_URL")
supabase_key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "missing or malformed token"})

    token = auth_header.split(" ")[1]

    try:
        result = supabase.auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid or expired token"})

    if not result or not result.user:
        raise HTTPException(status_code=401, detail={"error": "invalid or expired token"})

    return result.user


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
bearer_scheme = HTTPBearer()
app.include_router(enrich_router)

class AuthRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/signup", status_code=201)
def signup(payload: AuthRequest):
    if not payload.email or not payload.password:
        raise HTTPException(status_code=400, detail={"error": "email and password are required"})
    try:
        result = supabase.auth.sign_up({
            "email": payload.email,
            "password": payload.password
        })
        return {"user": result.user}
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": str(e)})


@app.post("/auth/login")
def login(payload: AuthRequest):
    if not payload.email or not payload.password:
        raise HTTPException(status_code=400, detail={"error": "email and password are required"})
    try:
        result = supabase.auth.sign_in_with_password({
            "email": payload.email,
            "password": payload.password
        })
        return {"access_token": result.session.access_token, "user": result.user}
    except Exception as e:
        raise HTTPException(status_code=401, detail={"error": "invalid credentials"})

@app.get("/public/info")
def public_info():
    return {"message": "This is a public endpoint. No auth required."}


@app.get("/protected/profile")
def protected_profile(user=Depends(get_current_user), _=Depends(bearer_scheme)):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
    }

@app.post("/auth/logout", status_code=204)
def logout(user=Depends(get_current_user), _=Depends(bearer_scheme)):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    return None

@app.get("/protected/dashboard")
def protected_dashboard(user=Depends(get_current_user), _=Depends(bearer_scheme)):
    return {
        "message": f"Welcome to your dashboard, {user.email}",
        "role": user.role,
    }


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
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks")
    rows = cur.fetchall()
    result = [row_to_task(row, cur) for row in rows]  # before close
    cur.close()
    conn.close()
    return result


@app.get("/tasks/{task_id}", summary="Get a single task", description="Returns one task by its id, or 404 if it doesn't exist.")
def get_task(task_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    row = cur.fetchone()
    if row is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    result = row_to_task(row, cur)  # read description before closing
    cur.close()
    conn.close()
    return result


@app.post("/tasks", status_code=201, summary="Create a task", description="Creates a new task with an auto-assigned id. Title is required and cannot be empty.")
def create_task(task: TaskCreate):
    if not task.title or not task.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING *",
        (task.title, task.done),
    )
    row = cur.fetchone()
    result = row_to_task(row, cur)
    cur.close()
    conn.close()
    return result


@app.put("/tasks/{task_id}", summary="Update a task", description="Replaces an existing task's title and done status. Returns 404 if the task doesn't exist.")
def update_task(task_id: int, task: TaskCreate):
    if not task.title or not task.title.strip():
        raise HTTPException(status_code=400, detail="Title is required")

    conn = get_connection()
    cur = conn.execute(
        "UPDATE tasks SET title = %s, done = %s WHERE id = %s RETURNING *",
        (task.title, task.done, task_id),
    )
    row = cur.fetchone()
    if row is None:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    result = row_to_task(row, cur)
    cur.close()
    conn.close()
    return result


@app.delete("/tasks/{task_id}", status_code=204, summary="Delete a task", description="Deletes a task by its id. Returns 404 if the task doesn't exist.")
def delete_task(task_id: int):
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM tasks WHERE id = %s RETURNING id",
        (task_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")