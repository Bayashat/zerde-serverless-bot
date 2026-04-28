# src/quiz/core/config.py
"""Centralised configuration: environment variables for the Quiz Lambda."""

import os
from typing import Any

from zerde_common.config import require, require_int
from zerde_common.secrets import load_ssm_secrets_if_needed

_SSM_KEY_MAP: dict[str, str] = {
    "bot-token": "BOT_TOKEN",
    "gemini-api-key": "GEMINI_API_KEY",
    "deepseek-api-key": "DEEPSEEK_API_KEY",
}
_SSM_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")
_LAZY_SECRET_ATTRS: frozenset[str] = frozenset({"BOT_TOKEN", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"})


def _load_secret(ssm_name: str, env_key: str) -> None:
    load_ssm_secrets_if_needed(_SSM_PREFIX, {ssm_name: env_key})


def get_bot_token() -> str:
    """Return Telegram bot token, loading SSM secrets on first use."""
    _load_secret("bot-token", "BOT_TOKEN")
    return require("BOT_TOKEN")


def get_gemini_api_key() -> str:
    """Return Gemini API key, loading SSM secrets on first use."""
    _load_secret("gemini-api-key", "GEMINI_API_KEY")
    return require("GEMINI_API_KEY")


def get_deepseek_api_key() -> str | None:
    """Return optional DeepSeek API key, loading SSM secrets on first use."""
    _load_secret("deepseek-api-key", "DEEPSEEK_API_KEY")
    return os.environ.get("DEEPSEEK_API_KEY")


# ── Optional ────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
GEMINI_MODEL: str | None = os.environ.get("QUIZ_GEMINI_MODEL")
QUIZ_LLM_RPD: int = require_int("QUIZ_LLM_RPD")

# ── Required (non-secret identifiers) ─────────────────────────────────────
TABLE_NAME: str = require("TABLE_NAME")

# ── DeepSeek fallback (non-key) ───────────────────────────────────────────
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str | None = os.environ.get("DEEPSEEK_MODEL")


def __getattr__(name: str) -> Any:
    if name in _LAZY_SECRET_ATTRS:
        if name == "BOT_TOKEN":
            return get_bot_token()
        if name == "GEMINI_API_KEY":
            return get_gemini_api_key()
        if name == "DEEPSEEK_API_KEY":
            return get_deepseek_api_key()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted({*globals().keys(), *_LAZY_SECRET_ATTRS, "__dir__", "__getattr__"})
