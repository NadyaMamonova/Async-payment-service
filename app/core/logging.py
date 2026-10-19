import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from app.core.context import get_request_id

STANDARD_LOG_RECORD_FIELDS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Serialize log records as one-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key not in STANDARD_LOG_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = self._make_json_safe(value)

        if record.exc_info is not None:
            payload["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            ).rstrip()

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _make_json_safe(value: Any) -> Any:
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
        return value


def configure_logging(log_level: str) -> None:
    """Configure process-wide structured logging."""

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    logging.getLogger("uvicorn.access").propagate = False