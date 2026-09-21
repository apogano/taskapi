import logging
import re
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.logging_config import request_id_var

logger = logging.getLogger("app.request")
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


async def request_context_middleware(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    request_id = (
        incoming if _VALID_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())
    )
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled error on %s %s", request.method, request.url.path
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s (%.1f) ms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
    finally:
        request_id_var.reset(token)
