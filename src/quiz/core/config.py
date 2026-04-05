"""Centralised configuration: environment variables for the Quiz Lambda."""

import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


# ── Required ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
QUIZAPI_KEY: str = _require("QUIZAPI_KEY")
QUIZ_TABLE_NAME: str = _require("QUIZ_TABLE_NAME")

# ── Optional ────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
