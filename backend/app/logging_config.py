"""Centralized logging configuration: structlog + stdlib handlers.

stdout  -> JSON  (for Promtail / Loki / Grafana)
files   -> human-readable text (for tail -f, grep, Notepad)

Three rotating file handlers:
  app.log    — INFO+  (all application logs)
  error.log  — ERROR+ (errors and critical only)
  access.log — INFO+  (HTTP request/response logs from middleware)
"""

import logging
import os
import sys
from contextvars import ContextVar
from logging.handlers import TimedRotatingFileHandler

import structlog

from app.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="-")
tenant_name_ctx: ContextVar[str] = ContextVar("tenant_name", default="-")
active_requests_count: int = 0

_MAX_BYTES = settings.log_max_size_mb * 1024 * 1024
_BACKUP_COUNT = settings.log_retention_days

_HUMAN_FMT = (
    "%(asctime)s.%(msecs)03d %(levelname)-5s [%(request_id)s] %(name)s | %(message)s"
)
_HUMAN_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class _RequestIdFilter(logging.Filter):
    """Inject request_id, tenant_id, tenant_name from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")  # type: ignore[attr-defined]
        record.tenant_id = tenant_id_ctx.get("-")  # type: ignore[attr-defined]
        record.tenant_name = tenant_name_ctx.get("-")  # type: ignore[attr-defined]
        return True


class _SizeAwareTimedHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that also rotates when file exceeds max size."""

    def __init__(self, filename: str, max_bytes: int, **kwargs):
        super().__init__(filename, **kwargs)
        self._max_bytes = max_bytes

    def shouldRollover(self, record: logging.LogRecord) -> int:
        if super().shouldRollover(record):
            return 1
        if self._max_bytes > 0 and self.stream is not None:
            self.stream.seek(0, 2)
            if self.stream.tell() + len(self.format(record)) >= self._max_bytes:
                return 1
        return 0


def _add_request_id(logger, method_name, event_dict):
    """Add request_id, tenant_id, tenant_name from contextvars to structlog event dict."""
    event_dict["request_id"] = request_id_ctx.get("-")
    event_dict["tenant_id"] = tenant_id_ctx.get("-")
    event_dict["tenant_name"] = tenant_name_ctx.get("-")
    return event_dict


def _merge_extra(logger, method_name, event_dict):
    """Merge stdlib LogRecord.extra fields into structlog event dict."""
    record = event_dict.get("_record")
    if record and hasattr(record, "__dict__"):
        skip = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs", "pathname",
            "process", "processName", "relativeCreated", "stack_info",
            "thread", "threadName", "exc_info", "exc_text", "message",
            "request_id", "tenant_id", "tenant_name", "taskName",
        }
        for key, value in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                event_dict[key] = value
    return event_dict


def _make_file_handler(
    filename: str, level: int = logging.INFO
) -> _SizeAwareTimedHandler:
    log_dir = settings.log_dir
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, filename)
    handler = _SizeAwareTimedHandler(
        path,
        max_bytes=_MAX_BYTES,
        when="midnight",
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    formatter = logging.Formatter(_HUMAN_FMT, datefmt=_HUMAN_DATE_FMT)
    handler.setFormatter(formatter)
    handler.addFilter(_RequestIdFilter())
    return handler


def _make_stdout_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.addFilter(_RequestIdFilter())
    return handler


def setup_logging() -> None:
    """Configure structlog + stdlib logging. Call once at startup."""
    log_level = getattr(logging, settings.app_log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
        _add_request_id,
        _merge_extra,
    ]

    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    human_formatter = logging.Formatter(_HUMAN_FMT, datefmt=_HUMAN_DATE_FMT)

    stdout_handler = _make_stdout_handler()
    stdout_handler.setFormatter(json_formatter)

    app_handler = _make_file_handler("app.log", level=logging.INFO)
    app_handler.setFormatter(human_formatter)

    error_handler = _make_file_handler("error.log", level=logging.ERROR)
    error_handler.setFormatter(human_formatter)

    access_handler = _make_file_handler("access.log", level=logging.INFO)
    access_handler.setFormatter(human_formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(stdout_handler)
    root.addHandler(app_handler)
    root.addHandler(error_handler)

    access_logger = logging.getLogger("access")
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    access_logger.handlers.clear()
    access_logger.addHandler(stdout_handler)
    access_logger.addHandler(access_handler)
    access_logger.addFilter(_RequestIdFilter())

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
