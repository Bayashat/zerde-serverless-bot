"""JSON log formatting shared across Lambdas (no import-time dependency on app config)."""

from __future__ import annotations

import json
import logging
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict = {
            "level": record.levelname,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "location": f"{record.module}.{record.funcName}",
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "_extra", None)
        if extra:
            log_entry.update(extra)
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def get_json_logger(name: str, log_level: str) -> logging.Logger:
    """Return a JSON-formatted logger, configured once per process."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        level = (log_level or "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False
    return logger


class ZerdeLoggerAdapter(logging.LoggerAdapter):
    """Adapter that passes extra kwargs into the log record's ``_extra`` bucket."""

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        extra: dict = {**self.extra, **kwargs.pop("extra", {})}
        kwargs["extra"] = {"_extra": extra}
        return msg, kwargs
