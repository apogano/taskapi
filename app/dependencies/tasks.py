from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.task import TaskRepository
from app.services.task import TaskService

DbSession = Annotated[Session, Depends(get_db)]


def get_task_repository(db: DbSession) -> TaskRepository:
    return TaskRepository(db)


def get_task_service(
    db: DbSession,
    repo: Annotated[TaskRepository, Depends(get_task_repository)],
) -> TaskService:
    return TaskService(db, repo)


Service = Annotated[TaskService, Depends(get_task_service)]
