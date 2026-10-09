import hmac

from fastapi import Request

from app.config import settings


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
