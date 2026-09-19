from fastapi import FastAPI,Request 
from fastapi.responses import JSONResponse

from app.database import Base, engine
from app.routers import tasks
from app.services.task import TaskNotFoundError

app = FastAPI(title="Task API")
app.include_router(tasks.router)

@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "Task not found"})
