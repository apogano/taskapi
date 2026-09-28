from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.rate_limiting.base import RateLimiter
from app.rate_limiting.postgres import PostgresRateLimiter

DbSession = Annotated[Session, Depends(get_db)]


def get_rate_limiter(db: DbSession) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        raise NotImplementedError("Redis backend not implemented yet")
    return PostgresRateLimiter(db)


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
