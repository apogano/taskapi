"""Management commands, run manually or from Cloud Run Job."""

import logging

from app.database import SessionLocal
from app.logging_config import setup_logging
from app.repositories.refresh_token import RefreshTokenRepository

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


if __name__ == "__main__":
    setup_logging()
    cleanup_refresh_tokens()
