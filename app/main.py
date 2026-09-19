from fastapi import FastAPI

from app.database import Base, engine
from app.routers import tasks

app = FastAPI(title="Task API")
app.include_router(tasks.router)
