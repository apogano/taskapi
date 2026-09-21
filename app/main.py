from fastapi import FastAPI

from app.config import settings
from app.errors import register_exception_handlers
from app.logging_config import setup_logging
from app.middleware import request_context_middleware
from app.routers import auth, tasks, users

setup_logging()

docs = settings.enable_docs

app = FastAPI(
    title="Task API",
    docs_url="/docs" if docs else None,
    redoc_url="/redoc" if docs else None,
    openapi_url="/openapi.json" if docs else None,
)

app.middleware("http")(request_context_middleware)
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
