from fastapi import FastAPI,Request 

from app.errors import register_exception_handlers
from app.logging_config import setup_logging
from app.middleware import request_context_middleware

from app.routers import tasks,auth,users

setup_logging()

app = FastAPI(title="Task API")
app.middleware("http")(request_context_middleware)
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
