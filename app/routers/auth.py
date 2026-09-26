from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app import schemas
from app.dependencies.auth import AuthServiceDep, UserServiceDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED
)
def register(payload: schemas.UserCreate, service: UserServiceDep):
    return service.register(payload)


@router.post("/login", response_model=schemas.TokenPair)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_service: UserServiceDep,
    auth_service: AuthServiceDep
):
    user = user_service.authenticate(form.username, form.password)
    pair = auth_service.issue_tokens(user)
    return schemas.TokenPair(access_token=pair.access_token, refresh_token=pair.refresh_token)

@router.post("/refresh", response_model=schemas.TokenPair)
def refresh(payload: schemas.RefreshRequest, auth_service: AuthServiceDep):
    pair, _ = auth_service.rotate(payload.refresh_token)
    return schemas.TokenPair(access_token=pair.access_token, refresh_token=pair.refresh_token)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.RefreshRequest, auth_service: AuthServiceDep):
    auth_service.revoke(payload.refresh_token)
