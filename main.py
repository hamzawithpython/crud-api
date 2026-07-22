from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def root():
    return {
        "name": "CRUD API",
        "description": "A simple in-memory task management API",
        "version": "0.1.0",
    }


@app.get("/health")
def health():
    return {"status": "ok"}