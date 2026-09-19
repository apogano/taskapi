from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app import schemas
from app.dependencies.auth import UserServiceDep
from app.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED
)
def register(payload: schemas.UserCreate, service: UserServiceDep):
    return service.register(payload)


@router.post("/login", response_model=schemas.Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: UserServiceDep,
):
    user = service.authenticate(form.username, form.password)
    return schemas.Token(access_token=create_access_token(str(user.id)))
