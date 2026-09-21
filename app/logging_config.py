import json
import logging
import sys
from contextvars import ContextVar

from app.config import settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Everything that doesn't belong to the total,comes from `extra={...}` and it goes into JSON
_STANDARD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "actime",
    "request_id",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One line Json per log. Cloud Logging reads `severity` and `message` fields"""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        data = {
            "severity": record.levelname,
            "message": message,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                data[key] = value
        return json.dumps(data, default=str, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # uvicorn passes through our logger. Access log is taken from us in the middleware
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    logging.getLogger("uvicorn.access").disabled = True
