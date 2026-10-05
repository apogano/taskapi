from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.attachment import (
    AttachmentNotFoundError,
    AttachmentNotReadyError,
    AttachmentTooLargeError,
)
from app.services.auth import InvalidRefreshTokenError
from app.services.task import TaskNotFoundError
from app.services.user import EmailAlreadyRegisteredError, InvalidCredentialsError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(request: Request, exc: TaskNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Task not found"})

    @app.exception_handler(EmailAlreadyRegisteredError)
    async def email_taken(request: Request, exc: EmailAlreadyRegisteredError):
        return JSONResponse(
            status_code=409, content={"detail": "Email already registered"}
        )

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials(request: Request, exc: InvalidCredentialsError):
        return JSONResponse(
            status_code=401,
            content={"detail": "Incorrect email or password"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(InvalidRefreshTokenError)
    async def invalid_refresh_token(request: Request, exc: InvalidRefreshTokenError):
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired refresh token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AttachmentNotFoundError)
    async def attachment_not_found(request: Request, exc: AttachmentNotFoundError):
        return JSONResponse(status_code=404, content={"detail": "Attachment not found"})

    @app.exception_handler(AttachmentNotReadyError)
    async def attachment_not_ready(request: Request, exc: AttachmentNotReadyError):
        return JSONResponse(
            status_code=409, content={"detail": "Attachment upload not confirmed yet"}
        )

    @app.exception_handler(AttachmentTooLargeError)
    async def attachment_too_large(request: Request, exc: AttachmentTooLargeError):
        return JSONResponse(status_code=413, content={"detail": "Attachment exceeds size limit"})