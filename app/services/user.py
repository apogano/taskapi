import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user import UserRepository
from app.schemas import UserCreate
from app.security import DUMMY_HASH, hash_password, verify_password

logger = logging.getLogger(__name__)


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserService:
    def __init__(self, db: Session, repo: UserRepository):
        self.db = db
        self.repo = repo

    def register(self, payload: UserCreate) -> User:
        email = payload.email.lower()
        if self.repo.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError
        try:
            user = self.repo.add(
                User(email=email, hashed_password=hash_password(payload.password))
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise EmailAlreadyRegisteredError(email) from None

        self.db.refresh(user)
        logger.info("User registered id=%s", user.id)
        return user

    def authenticate(self, email: str, password: str) -> User:
        user = self.repo.get_by_email(email.lower())
        if user is None:
            # Same time in case the user exists
            verify_password(password, DUMMY_HASH)

        valid = (
            user is not None
            and verify_password(password, user.hashed_password)
            and user.is_active
        )

        if not valid:
            logger.warning("Failed login attempt")
            raise InvalidCredentialsError()
        return user

    def find(self, user_id: UUID) -> User | None:
        return self.repo.get(user_id)
