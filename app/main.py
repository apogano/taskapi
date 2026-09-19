from fastapi import FastAPI,Request 
from fastapi.responses import JSONResponse

from app.database import Base, engine
from app.routers import tasks,auth,users
from app.services.task import TaskNotFoundError
from app.services.user import EmailAlreadyRegisteredError, InvalidCredentialsError


app = FastAPI(title="Task API")
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)


@app.exception_handler(TaskNotFoundError)
async def task_not_found_handler(request: Request, exc: TaskNotFoundError):
    return JSONResponse(status_code=404, content={"detail": "Task not found"})

@app.exception_handler(EmailAlreadyRegisteredError)
async def email_taken_handler(request: Request, exc: EmailAlreadyRegisteredError):
    return JSONResponse(status_code=409, content={"detail": "Email already registered"})


@app.exception_handler(InvalidCredentialsError)
async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
    return JSONResponse(
        status_code=401,
        content={"detail": "Incorrect email or password"},
        headers={"WWW-Authenticate": "Bearer"},
    )
