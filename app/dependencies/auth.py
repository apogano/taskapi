from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.security import decode_access_token
from app.services.auth import AuthService
from app.services.user import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


DbSession = Annotated[Session, Depends(get_db)]


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    db: DbSession, repo: Annotated[UserRepository, Depends(get_user_repository)]
) -> UserService:
    return UserService(db, repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], service: UserServiceDep
) -> User:
    credentials_error = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    sub = decode_access_token(token)
    if sub is None:
        raise credentials_error
    try:
        user_id = UUID(sub)
    except ValueError:
        raise credentials_error

    user = service.find(user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_refresh_token_repository(db: DbSession) -> RefreshTokenRepository:
    return RefreshTokenRepository(db)


def get_auth_service(
    db: DbSession,
    repo: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(db, repo, user_repo)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
