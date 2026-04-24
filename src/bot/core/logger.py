"""Lightweight JSON logger for structured CloudWatch output."""

import logging

from core.config import LOG_LEVEL
from zerde_common.logger import ZerdeLoggerAdapter, get_json_logger


def get_logger(name: str = "bot") -> logging.Logger:
    """Return a JSON-formatted logger, configured once."""
    return get_json_logger(name, LOG_LEVEL)


class LoggerAdapter(ZerdeLoggerAdapter):
    """Adapter that passes extra kwargs into the log record."""
