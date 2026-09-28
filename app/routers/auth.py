from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app import schemas
from app.config import settings
from app.dependencies.auth import AuthServiceDep, UserServiceDep
from app.dependencies.rate_limit import RateLimiterDep
from app.rate_limiting.keys import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def enforce_rate_limit(
    request: Request,
    limiter: RateLimiterDep,
    key_suffix: str,
    limit: int,
    window_seconds: int,
) -> None:
    key = f"{key_suffix}:{client_ip(request)}"
    result = limiter.hit(key, limit=limit, window_seconds=window_seconds)
    if not result.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts, please try again later.",
            headers={"Retry-After": str(result.retry_after_seconds)},
        )


@router.post(
    "/register", response_model=schemas.UserRead, status_code=status.HTTP_201_CREATED
)
def register(
    payload: schemas.UserCreate,
    request: Request,
    service: UserServiceDep,
    limiter: RateLimiterDep,
):
    enforce_rate_limit(
        request,
        limiter,
        "register",
        settings.rate_limit_register_attempts,
        settings.rate_limit_register_window_seconds,
    )
    return service.register(payload)


@router.post("/login", response_model=schemas.TokenPair)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    user_service: UserServiceDep,
    auth_service: AuthServiceDep,
    limiter: RateLimiterDep,
):
    enforce_rate_limit(
        request,
        limiter,
        "login",
        settings.rate_limit_login_attempts,
        settings.rate_limit_login_window_seconds,
    )
    user = user_service.authenticate(form.username, form.password)
    pair = auth_service.issue_tokens(user)
    return schemas.TokenPair(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/refresh", response_model=schemas.TokenPair)
def refresh(
    payload: schemas.RefreshRequest,
    request: Request,
    auth_service: AuthServiceDep,
    limiter: RateLimiterDep,
):
    enforce_rate_limit(
        request,
        limiter,
        "refresh",
        settings.rate_limit_refresh_attempts,
        settings.rate_limit_refresh_window_seconds,
    )
    pair, _ = auth_service.rotate(payload.refresh_token)
    return schemas.TokenPair(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.RefreshRequest, auth_service: AuthServiceDep):
    auth_service.revoke(payload.refresh_token)
