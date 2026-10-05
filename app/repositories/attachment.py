from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attachment


class AttachmentRepository:
    def __init__(self, db:Session):
        self.db = db

    def get(self,task_id: UUID, attachment_id: UUID) -> Attachment| None:
        return self.db.scalar(
            select(Attachment).where(
                Attachment.id == attachment_id,
                Attachment.task_id == task_id
            )
        )

    def add(self, attachment: Attachment)->Attachment:
        self.db.add(attachment)
        self.db.flush()
        return attachment

    def delete(self,attachment: Attachment) -> None:
        self.db.delete(attachment)