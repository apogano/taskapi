from fastapi import APIRouter

from app import schemas
from app.dependencies.auth import CurrentUser

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=schemas.UserRead)
def read_me(current_user: CurrentUser):
    return current_user
