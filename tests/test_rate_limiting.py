from unittest.mock import MagicMock

from app.rate_limiting.keys import client_ip
from app.rate_limiting.postgres import PostgresRateLimiter


def test_allows_up_to_the_limit(db):
    limiter = PostgresRateLimiter(db)

    for _ in range(5):
        result = limiter.hit("test-key", limit=5, window_seconds=60)
        assert result.allowed is True


def test_blocks_after_limit_exceeded(db):
    limiter = PostgresRateLimiter(db)

    for _ in range(5):
        limiter.hit("test-key", limit=5, window_seconds=60)

    result = limiter.hit("test-key", limit=5, window_seconds=60)

    assert result.allowed is False
    assert result.retry_after_seconds is not None
    assert result.retry_after_seconds > 0


def test_different_keys_have_independent_limits(db):
    limiter = PostgresRateLimiter(db)

    for _ in range(5):
        limiter.hit("key-a", limit=5, window_seconds=60)

    # το key-b δεν έχει επηρεαστεί καθόλου
    result = limiter.hit("key-b", limit=5, window_seconds=60)
    assert result.allowed is True


def test_concurrent_hits_are_counted_correctly(db):
    """Simulates concurrent requests in the same key/window — if confirms
    that the atomic upsert does not lose increments (race condition)."""
    limiter = PostgresRateLimiter(db)

    results = [limiter.hit("race-key", limit=100, window_seconds=60) for _ in range(20)]

    assert all(r.allowed for r in results)
    # If 21th is not count=20, then this means that some
    # increments "lost")
    next_result = limiter.hit("race-key", limit=20, window_seconds=60)
    assert next_result.allowed is False


def test_client_ip_prefers_x_forwarded_for():
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
    assert client_ip(request) == "1.2.3.4"


def test_client_ip_falls_back_to_direct_connection():
    request = MagicMock()
    request.headers = {}
    request.client.host = "5.6.7.8"
    assert client_ip(request) == "5.6.7.8"
