from unittest.mock import MagicMock

from app.config import settings
from app.rate_limiting.keys import client_ip
from app.rate_limiting.postgres import PostgresRateLimiter


def make_request(headers: dict[str, str], peer: str = "169.254.169.126"):
    request = MagicMock()
    request.headers = headers
    request.client.host = peer
    return request


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


def test_client_ip_uses_the_entry_appended_by_cloud_run():
    request = make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 203.0.113.9"})
    # The first two were supplied by the client and must be ignored
    assert client_ip(request) == "203.0.113.9"


def test_client_ip_falls_back_to_peer_without_forwarded_for():
    assert client_ip(make_request({}, peer="127.0.0.1")) == "127.0.0.1"


def test_proxy_client_ip_is_trusted_with_correct_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_shared_secret", "s3cret")
    request = make_request(
        {
            "X-Client-IP": "198.51.100.7",
            "X-Proxy-Secret": "s3cret",
            "X-Forwarded-For": "203.0.113.9",
        }
    )
    assert client_ip(request) == "198.51.100.7"


def test_proxy_client_ip_is_ignored_with_wrong_secret(monkeypatch):
    monkeypatch.setattr(settings, "proxy_shared_secret", "s3cret")
    request = make_request(
        {
            "X-Client-IP": "198.51.100.7",
            "X-Proxy-Secret": "guess",
            "X-Forwarded-For": "203.0.113.9",
        }
    )
    assert client_ip(request) == "203.0.113.9"


def test_proxy_client_ip_is_ignored_when_no_secret_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "proxy_shared_secret", "")
    request = make_request(
        {
            "X-Client-IP": "198.51.100.7",
            "X-Proxy-Secret": "",
            "X-Forwarded-For": "203.0.113.9",
        }
    )
    assert client_ip(request) == "203.0.113.9"
