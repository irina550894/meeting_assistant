import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

OPERATION_ID: ContextVar[str | None] = ContextVar("operation_id", default=None)
EMAIL_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@"
    r"(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)
SECRET_KEY_PARTS = (
    "secret",
    "token",
    "password",
    "authorization",
    "api_key",
    "refresh",
    "access_token",
    "client_secret",
    "webhook",
)

RESERVED_LOG_RECORD_KEYS = {
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
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "operation_id": getattr(record, "operation_id", None)
            or OPERATION_ID.get()
            or "system",
        }

        for key, value in record.__dict__.items():
            if key not in RESERVED_LOG_RECORD_KEYS and not key.startswith("_"):
                payload[key] = _sanitize_log_value(key, value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        payload["message"] = _mask_email(str(payload["message"]))
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(level: str = "INFO") -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(JsonFormatter())
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def new_operation_id() -> str:
    return uuid.uuid4().hex


def set_operation_id(operation_id: str | None = None):
    return OPERATION_ID.set(operation_id or new_operation_id())


def reset_operation_id(token) -> None:
    OPERATION_ID.reset(token)


def _sanitize_log_value(key: str, value: Any) -> Any:
    if _is_secret_key(key):
        return "***"
    if isinstance(value, str):
        return _mask_email(value)
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_log_value(str(item_key), item_value)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_log_value(key, item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_log_value(key, item) for item in value)
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower()
    return any(part in normalized for part in SECRET_KEY_PARTS)


def _mask_email(value: str) -> str:
    return EMAIL_PATTERN.sub(
        lambda match: f"{match.group('prefix')}***@{match.group('domain')}",
        value,
    )
