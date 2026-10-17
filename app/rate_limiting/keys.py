import hashlib
import hmac

from fastapi import Request

from app.config import settings

# A subkey derived from SECRET_KEY and used only here, so these hashes can
# never be confused with anything else the main key signs.
_HASH_KEY = hmac.new(
    settings.secret_key.encode(), b"rate-limit-keys", hashlib.sha256
).digest()


def client_ip(request: Request) -> str:
    # 1. Our own frontend proxy, which proves itself with a shared secret.
    #    With no secret configured this path is disabled entirely; otherwise
    #    an empty X-Proxy-Secret header would match an empty setting.
    secret = settings.proxy_shared_secret
    if secret:
        supplied = request.headers.get("X-Proxy-Secret", "")
        forwarded_client = request.headers.get("X-Client-IP")
        if forwarded_client and hmac.compare_digest(supplied.encode(), secret.encode()):
            return forwarded_client.strip()

    # 2. Cloud Run (with no load balancer in front) appends exactly one entry,
    #    the address it saw, at the END. Everything before it came from the
    #    client and can't be trusted. A load balancer would append two
    #    entries and require reading the second to last instead.
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[-1].strip()

    # 3. No proxy at all (local development)
    return request.client.host if request.client else "unknown"


def rate_limit_key(scope: str, identifier: str) -> str:
    """Builds a rate limit key that doesn't contain the IP or email itself
    The limiter only evere compares key for equality, so it never ends the original value.
    A keyed has (not plain SHA-256) is essential: there are only ~4 billion IPv4 addresses,
    so an unkeyed hash of every one of them can be computed in minutes and reversed by lookup.
    """
    digest = hmac.new(_HASH_KEY, identifier.encode(), hashlib.sha256).hexdigest()
    return f"{scope}:{digest}"
