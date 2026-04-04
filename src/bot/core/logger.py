"""Lightweight JSON logger for structured CloudWatch output."""

import json
import logging
import os


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


def get_logger(name: str = "bot") -> logging.Logger:
    """Return a JSON-formatted logger, configured once."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        logger.propagate = False
    return logger


class LoggerAdapter(logging.LoggerAdapter):
    """Adapter that passes extra kwargs into the log record."""

    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", {})
        kwargs["extra"] = {"_extra": extra}
        return msg, kwargs
