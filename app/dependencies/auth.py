from uuid import UUID
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from app.models import User
from app.repositories.user import UserRepository
from app.security import decode_access_token
from app.services.user import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl = "/auth/login")

from app.database import get_db

DbSession = Annotated[Session, Depends(get_db)]

def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)
    
def get_user_service(
        db:DbSession, 
        repo :Annotated[UserRepository, Depends(get_user_repository)]
    ) -> UserService:
        return UserService(db,repo)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]

def get_current_user(
        token:Annotated[str,Depends(oauth2_scheme)],
        service: UserServiceDep
    ) -> User:
        credentials_error = HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Could not validate credentials",
            headers={"WWW-Authenticate":"Bearer"}
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
