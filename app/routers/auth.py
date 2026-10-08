from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import schemas
from app.config import settings
from app.cookies import clear_refresh_cookie, set_refresh_cookie
from app.dependencies.auth import AuthServiceDep, UserServiceDep
from app.dependencies.rate_limit import RateLimiterDep
from app.rate_limiting.keys import client_ip
from app.services.auth import InvalidRefreshTokenError

router = APIRouter(prefix="/auth", tags=["auth"])

RefreshCookie = Annotated[str | None, Cookie(alias=settings.refresh_cookie_name)]
LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]


def enforce_rate_limit(
    limiter: RateLimiterDep,
    *checks: tuple[str, int, int],
) -> None:
    """Each check is (key, limit, window_seconds). All checks must pass;
    the first one that fails raises a 429 immediately."""
    for key, limit, window_seconds in checks:
        result = limiter.hit(key, limit=limit, window_seconds=window_seconds)
        if not result.allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many attempts, please try again later",
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
        limiter,
        (
            f"register:{client_ip(request)}",
            settings.rate_limit_register_attempts,
            settings.rate_limit_register_window_seconds,
        ),
    )
    return service.register(payload)


# --- Shared logic:identical rate limits regardless of client type


def _login(form, request, user_service, auth_service, limiter) -> schemas.TokenPair:
    # Two independent checks, both must pass:
    # - per-IP: stops one IP hammering many accounts
    # - per-account: stops one account being hammered from many IPs
    enforce_rate_limit(
        limiter,
        (
            f"login:{client_ip(request)}",
            settings.rate_limit_login_attempts,
            settings.rate_limit_login_window_seconds,
        ),
        (
            f"login-account:{form.username.strip().lower()}",
            settings.rate_limit_login_account_attempts,
            settings.rate_limit_login_account_window_seconds,
        ),
    )
    user = user_service.authenticate(form.username, form.password)
    pair = auth_service.issue_tokens(user)
    return pair


def _refresh(raw_token: str, request, auth_service, limiter) -> schemas.TokenPair:
    enforce_rate_limit(
        limiter,
        (
            f"refresh:{client_ip(request)}",
            settings.rate_limit_refresh_attempts,
            settings.rate_limit_refresh_window_seconds,
        ),
    )
    pair, _ = auth_service.rotate(raw_token)
    return pair


# --- Native clients: tokens in the JSON body, never cookie


@router.post("/login", response_model=schemas.TokenPair)
def login(
    form: LoginForm,
    request: Request,
    user_service: UserServiceDep,
    auth_service: AuthServiceDep,
    limiter: RateLimiterDep,
):
    pair = _login(form, request, user_service, auth_service, limiter)
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
    pair = _refresh(payload.refresh_token, request, auth_service, limiter)
    return schemas.TokenPair(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: schemas.RefreshRequest, auth_service: AuthServiceDep):
    auth_service.revoke(payload.refresh_token)


# ---Browsers: refresh token only in httpOnly cookie ---
@router.post("/web/login", response_model=schemas.AccessToken)
def web_login(
    form: LoginForm,
    request: Request,
    response: Response,
    user_service: UserServiceDep,
    auth_service: AuthServiceDep,
    limiter: RateLimiterDep,
):
    pair = _login(form, request, user_service, auth_service, limiter)
    set_refresh_cookie(response, pair.refresh_token)
    return schemas.AccessToken(access_token=pair.access_token)


def _invalid_web_refresh() -> JSONResponse:
    # A dead cookie is useless: tell the browser to drop it so it stops
    # sending it. Only the web flow does this; native clients never get cookies.
    error = JSONResponse(
        status_code=401,
        content={"detail": "Invalid or expired refresh token"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    clear_refresh_cookie(error)
    return error


@router.post("/web/refresh", response_model=schemas.AccessToken)
def web_refresh(
    request: Request,
    response: Response,
    auth_service: AuthServiceDep,
    user_service: UserServiceDep,
    limiter: RateLimiterDep,
    refresh_token: RefreshCookie = None,
):
    if refresh_token is None:
        return _invalid_web_refresh()

    try:
        pair = _refresh(refresh_token, request, auth_service, limiter)
    except InvalidRefreshTokenError:
        return _invalid_web_refresh()

    set_refresh_cookie(response, pair.refresh_token)
    return schemas.AccessToken(access_token=pair.access_token)


@router.post("/web/logout", status_code=status.HTTP_204_NO_CONTENT)
def web_logout(
    response: Response,
    auth_service: AuthServiceDep,
    refresh_token: RefreshCookie = None,
):
    if refresh_token is not None:
        auth_service.revoke(refresh_token)
    clear_refresh_cookie(response)
