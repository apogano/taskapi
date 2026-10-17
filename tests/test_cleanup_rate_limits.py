from datetime import UTC, datetime, timedelta

from app.models import RateLimitHit
from app.rate_limiting.postgres import PostgresRateLimiter


def test_delete_expired_removes_only_old_windows(db):
    limiter = PostgresRateLimiter(db)
    limiter.hit("current", limit=5, window_seconds=60)
    db.add(
        RateLimitHit(
            key="old", window_start=datetime.now(UTC) - timedelta(days=2), count=3
        )
    )
    db.flush()

    deleted = limiter.delete_expired(older_than=timedelta(days=1))

    assert deleted == 1
    assert [key for (key,) in db.query(RateLimitHit.key).all()] == ["current"]
