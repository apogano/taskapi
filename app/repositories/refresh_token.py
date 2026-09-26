from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db:Session):
        self.db = db
        
    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        return self.db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
    
    def add(self, token:RefreshToken) -> RefreshToken:
        self.db.add(token)
        self.db.flush()
        return token
        
    def revoke(self, token:RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
    
    def revoke_family(self, family_id:UUID) -> None:
        self.db.query(RefreshToken).filter(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at":datetime.now(UTC)})

