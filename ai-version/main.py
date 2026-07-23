from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Task CRUD API")


class Task(BaseModel):
    id: int
    title: str
    completed: bool = False


class TaskCreate(BaseModel):
    title: str
    completed: bool = False


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    completed: Optional[bool] = None


tasks = []
next_id = 1


@app.get("/")
def read_root():
    return {"message": "Welcome to the Task CRUD API"}


@app.get("/tasks")
def get_tasks():
    return tasks


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks")
def create_task(task: TaskCreate):
    global next_id
    new_task = {"id": next_id, "title": task.title, "completed": task.completed}
    tasks.append(new_task)
    next_id += 1
    return new_task


@app.put("/tasks/{task_id}")
def update_task(task_id: int, task: TaskUpdate):
    for existing_task in tasks:
        if existing_task["id"] == task_id:
            if task.title is not None:
                existing_task["title"] = task.title
            if task.completed is not None:
                existing_task["completed"] = task.completed
            return existing_task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    for existing_task in tasks:
        if existing_task["id"] == task_id:
            tasks.remove(existing_task)
            return {"message": "Task deleted successfully"}
    raise HTTPException(status_code=404, detail="Task not found")