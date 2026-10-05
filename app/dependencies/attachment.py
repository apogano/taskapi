from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.tasks import get_task_repository
from app.repositories.attachment import AttachmentRepository
from app.repositories.task import TaskRepository
from app.services.attachment import AttachmentService

DbSession = Annotated[Session, Depends(get_db)]


def get_attachment_repository(db: DbSession) -> AttachmentRepository:
    return AttachmentRepository(db)


def get_attachment_service(
    db: DbSession,
    repo: Annotated[AttachmentRepository, Depends(get_attachment_repository)],
    task_repo: Annotated[TaskRepository, Depends(get_task_repository)],
) -> AttachmentService:
    return AttachmentService(db, repo, task_repo)


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]
