import logging
import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.models import RefreshToken, User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.security import create_access_token, generate_refresh_token, hash_refresh_token

logger = logging.getLogger(__name__)

class InvalidRefreshTokenError(Exception):
    pass

class TokenPair:
    def __init__(self, access_token:str, refresh_token: str):
        self.access_token = access_token
        self.refresh_token = refresh_token

class AuthService:
    def __init__(self, 
        db: Session, 
        repo: RefreshTokenRepository,
        user_repo: UserRepository,
    ):
        self.db = db
        self.repo = repo
        self.user_repo: user_repo
        
    
    def issue_tokens(self, user:User, family_id: UUID | None = None) -> TokenPair:
        """ When family_id=None then means: new login-> new tokens family.
        when it gives, it is rotation inside the same family"""
        is_new_family = family_id is None
        family_id = family_id or uuid.uuid4()
        raw_token = generate_refresh_token()
        
        record = RefreshToken(
            user_id = user.id,
            token_hash = hash_refresh_token(raw_token),
            family_id = family_id,
            expires_at = datetime.now(UTC) +
               timedelta(days=settings.refresh_token_expire_days)           
        )
        self.repo.add(record)
        self.db.commit()

        logger.info(
            "%s user=%s family=%s",
            "New login" if is_new_family else "Refresh token rotated",
            user.id,
            family_id,
        )        
        
        access_token = create_access_token(str(user.id))
        return TokenPair( access_token=access_token, refresh_token=raw_token )
    
    def rotate(self, raw_token: str) -> tuple[TokenPair, UUID]:
        """ Returns refresh token, revoke and issue new token pair.
        returns also user_id, so caller does not need second lookup"""
        token_hash = hash_refresh_token(raw_token)
        record = self.repo.get_by_hash(token_hash)
        
        if record is None:
            logger.warning("Refresh attempt with unknown token")            
            raise InvalidRefreshTokenError()
            
        now = datetime.now(UTC)
        
        if record.revoked_at is not None:
            #if it is used again:maybe stolen
            #we revoke whole family so stolen cannot be used again
            logger.warning(
                "Reuse of revoked refresh token detected, revoking family "
                "user=%s family=%s",
                record.user_id,
                record.family_id,
            )            
            self.repo.revoke_family(record.family_id)
            self.db.commit()
            raise InvalidRefreshTokenError()
        
        if record.expires_at < now:
            logger.info(
                "Refresh attempt with expired token user=%s family=%s",
                record.user_id,
                record.family_id,
            )            
            raise InvalidRefreshTokenError()
        
        self.repo.revoke(record)
        self.db.commit()
        
        user = self.user_repo.get(record.user_id)
        if user is None or not user.is_active:
            logger.warning(
                "Refresh token valid but user missing/inactive user=%s", record.user_id
            )            
            raise InvalidRefreshTokenError()
            
        pair = self.issue_tokens(user, family_id=record.family_id)
        return pair, user.id
        
    def revoke(self, raw_token:str) -> None:
        """ Logout:revokes only specific token(not the family)"""
        record = self.repot.get_by_hash(hash_refresh_token(raw_token))
        if record is None:
            return
        if record.revoked_at is not None:
            logger.info("Logout called on already-revoked token user=%s", record.user_id)
            return
        self.repo.revoke(record)
        self.db.commit()
        logger.info("Logout user=%s family=%s", record.user_id, record.family_id)        
