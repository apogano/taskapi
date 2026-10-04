from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import RateLimitHit
from app.rate_limiting.base import RateLimiter, RateLimitResult


class PostgresRateLimiter(RateLimiter):
    def __init__(self, db: Session):
        self.db = db

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = datetime.now(UTC)
        epoch = int(now.timestamp())
        window_start_epoch = (epoch // window_seconds) * window_seconds
        window_start = datetime.fromtimestamp(window_start_epoch, tz=UTC)

        stmt = insert(RateLimitHit).values(key=key, window_start=window_start, count=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[RateLimitHit.key, RateLimitHit.window_start],
            set_={"count": RateLimitHit.count + 1},
        ).returning(RateLimitHit.count)

        count = self.db.execute(stmt).scalar_one()
        self.db.commit()

        if count > limit:
            retry_after = window_start_epoch + window_seconds - epoch
            return RateLimitResult(allowed=False, retry_after_seconds=retry_after)

        return RateLimitResult(allowed=True)
