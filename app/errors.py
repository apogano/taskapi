from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.task import TaskNotFoundError
from app.services.user import EmailAlreadyRegisteredError, InvalidCredentialsError

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(request: Request, exc: TaskNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Task not found"})

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def email_taken(request: Request, exc: EmailAlreadyRegisteredError):
        return JSONResponse(status_code=409, content={"detail": "Email already registered"})

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials(request: Request, exc: InvalidCredentialsError):
        return JSONResponse(
            status_code=401,
            content={"detail": "Incorrect email or password"},
            headers={"WWW-Authenticate": "Bearer"},
        )
