"""Centralised configuration: environment variables for the News Lambda."""

import os

from zerde_common.config import require
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


def get_deepseek_api_key() -> str:
    """Return DeepSeek API key, loading SSM secrets on first use."""
    _load_secret("deepseek-api-key", "DEEPSEEK_API_KEY")
    return require("DEEPSEEK_API_KEY")


# ── Optional (have defaults) ─────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

LLM_MODEL: str | None = os.environ.get("NEWS_GEMINI_MODEL")

# ── DeepSeek fallback (non-key) ───────────────────────────────────────────
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str | None = os.environ.get("DEEPSEEK_MODEL")


def __getattr__(name: str) -> str:
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
