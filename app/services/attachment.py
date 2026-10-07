import logging
import uuid
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Attachment
from app.repositories.attachment import AttachmentRepository
from app.repositories.task import TaskRepository
from app.schemas import AttachmentCreate
from app.services.task import TaskNotFoundError
from app.storage import (
    delete_object,
    generate_download_url,
    generate_upload_url,
    get_blob_size,
)

logger = logging.getLogger(__name__)


class AttachmentNotFoundError(Exception):
    pass


class AttachmentNotReadyError(Exception):
    pass


class AttachmentTooLargeError(Exception):
    pass


class AttachmentService:
    def __init__(
        self,
        db: Session,
        repo: AttachmentRepository,
        task_repo: TaskRepository,
    ):
        self.db = db
        self.repo = repo
        self.task_repo = task_repo

    def _get_owned_attachment(
        self, owner_id: UUID, task_id: UUID, attachment_id: UUID
    ) -> Attachment:
        task = self.task_repo.get(owner_id, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        attachment = self.repo.get(task_id, attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError()
        return attachment

    def create(
        self, owner_id: UUID, task_id: UUID, payload: AttachmentCreate
    ) -> tuple[Attachment, str]:
        task = self.task_repo.get(owner_id, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        attachment_id = uuid.uuid4()
        storage_path = f"tasks/{task_id}/{attachment_id}/{payload.filename}"

        attachment = Attachment(
            id=attachment_id,
            task_id=task_id,
            filename=payload.filename,
            content_type=payload.content_type,
            status="pending",
            storage_path=storage_path,
        )
        self.repo.add(attachment)
        self.db.commit()
        self.db.refresh(attachment)

        upload_url = generate_upload_url(
            storage_path,
            payload.content_type,
            settings.attachment_upload_url_expire_minutes,
        )
        logger.info("Attachment created id=%s task=%s", attachment.id, task_id)
        return attachment, upload_url

    def confirm(self, owner_id: UUID, task_id: UUID, attachment_id: UUID) -> Attachment:
        attachment = self._get_owned_attachment(owner_id, task_id, attachment_id)

        size = get_blob_size(attachment.storage_path)
        if size is None:
            raise AttachmentNotFoundError()

        max_bytes = settings.attachment_max_size_mb * 1024 * 1024
        if size > max_bytes:
            delete_object(attachment.storage_path)
            self.repo.delete(attachment)
            self.db.commit()
            logger.warning(
                "Attachment rejected, too large; id=%s size=%d max=%d",
                attachment_id,
                size,
                max_bytes,
            )
            raise AttachmentTooLargeError()

        attachment.status = "uploaded"
        self.db.commit()
        self.db.refresh(attachment)
        logger.info("Attachment confirmed id=%s size=%d", attachment.id, size)
        return attachment

    def get_download_url(
        self, owner_id: UUID, task_id: UUID, attachment_id: UUID
    ) -> str:
        attachment = self._get_owned_attachment(owner_id, task_id, attachment_id)

        if attachment.status != "uploaded":
            raise AttachmentNotReadyError()

        return generate_download_url(
            attachment.storage_path, settings.attachment_download_url_expire_minutes
        )

    def delete(self, owner_id: UUID, task_id: UUID, attachment_id: UUID) -> None:
        attachment = self._get_owned_attachment(owner_id, task_id, attachment_id)

        delete_object(attachment.storage_path)
        self.repo.delete(attachment)
        self.db.commit()
        logger.info("Attachment deleted id=%s task=%s", attachment_id, task_id)

    def cleanup_stale_pending(self, older_than_hours: int = 24) -> int:
        stale = self.repo.find_stale_pending(older_than_hours)
        for attachment in stale:
            # Best-effort: the object may never have been uploaded at all.
            delete_object(attachment.storage_path)
            self.repo.delete(attachment)

        if stale:
            self.db.commit()

        logger.info("Attachment cleanup: deleted %d stale pending rows", len(stale))
        return len(stale)

    def list(
        self, owner_id: UUID, task_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Attachment], int]:
        task = self.task_repo.get(owner_id, task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        items = self.repo.list(task_id, limit=limit, offset=offset)
        total = self.repo.count(task_id)
        return items, total
