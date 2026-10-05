"""Management commands, run manually or from Cloud Run Job."""

import logging
import sys

from app.database import SessionLocal
from app.logging_config import setup_logging
from app.repositories.attachment import AttachmentRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.task import TaskRepository
from app.services.attachment import AttachmentService

logger = logging.getLogger(__name__)


def cleanup_refresh_tokens() -> None:
    db = SessionLocal()
    try:
        repo = RefreshTokenRepository(db)
        deleted = repo.delete_expired_and_revoked()
        db.commit()
        logger.info("Refresh token cleanup: deleted %d rows", deleted)
    finally:
        db.close()


def cleanup_stale_attachments() -> None:
    db = SessionLocal()
    try:
        service = AttachmentService(db, AttachmentRepository(db), TaskRepository(db))
        service.cleanup_stale_pending()
    finally:
        db.close()


COMMANDS = {
    "cleanup-refresh-tokens": cleanup_refresh_tokens,
    "cleanup-stale-attachments": cleanup_stale_attachments,
}

if __name__ == "__main__":
    setup_logging()

    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        available = ", ".join(COMMANDS)
        print(
            f"Usage: python -m app.cli <command>\nAvailable: {available}",
            file=sys.stderr,
        )
        sys.exit(1)

    COMMANDS[sys.argv[1]]()
