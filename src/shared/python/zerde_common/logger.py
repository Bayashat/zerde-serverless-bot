"""JSON log formatting shared across Lambdas (no import-time dependency on app config)."""

from __future__ import annotations

import json
import logging
from typing import Any

from zerde_common.logging_utils import redact_log_text, sanitize_log_value


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        try:
            return self._format_record(record)
        except Exception:
            # logging.Handler.handleError prints the original msg/args to stderr on formatter errors.
            # A malformed diagnostic must not open that unsanitized fallback path.
            return '{"level":"ERROR","message":"Log record omitted: formatting failed"}'

    def _format_record(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "level": record.levelname,
            "message": redact_log_text(record.getMessage()),
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "location": f"{record.module}.{record.funcName}",
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = redact_log_text(self.formatException(record.exc_info))
        extra = getattr(record, "_extra", None)
        if extra:
            # Keep formatter-owned fields authoritative even if a caller supplies the same extra key.
            log_entry = {**sanitize_log_value(extra), **log_entry}
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def _configure_json_logger(logger: logging.Logger, log_level: str) -> None:
    # Libraries such as urllib3 install a NullHandler, which is not an output sink.
    if all(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        level = (log_level or "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False


def get_json_logger(name: str, log_level: str) -> logging.Logger:
    """Return a JSON logger and route urllib3 retry diagnostics through the same safe sink."""
    logger = logging.getLogger(name)
    _configure_json_logger(logger, log_level)
    # urllib3's own retry warnings include request URLs before the exception reaches our adapters.
    # Its child loggers normally propagate to Lambda's unsanitized root handler.
    _configure_json_logger(logging.getLogger("urllib3"), "WARNING")
    return logger


class ZerdeLoggerAdapter(logging.LoggerAdapter):
    """Adapter that passes extra kwargs into the log record's ``_extra`` bucket."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra: dict = {**self.extra, **kwargs.pop("extra", {})}
        kwargs["extra"] = {"_extra": extra}
        return msg, kwargs
