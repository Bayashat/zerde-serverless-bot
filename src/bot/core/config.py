"""Centralised configuration: environment variables and constants."""

import os
from typing import Any

from zerde_common.config import require, require_int, require_json
from zerde_common.secrets import load_ssm_secrets_if_needed

# ── SSM: secrets loaded on first access (see __getattr__) — no import-time boto3. ─
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")
_SSM_KEY_MAP: dict[str, str] = {
    "bot-token": "BOT_TOKEN",
    "webhook-secret-token": "WEBHOOK_SECRET_TOKEN",
    "groq-api-key": "GROQ_API_KEY",
    "gemini-api-key": "GEMINI_API_KEY",
    "deepseek-api-key": "DEEPSEEK_API_KEY",
}
_LAZY_SECRET_ATTRS: frozenset[str] = frozenset(
    {"BOT_TOKEN", "WEBHOOK_SECRET_TOKEN", "GROQ_API_KEY", "GEMINI_API_KEY", "DEEPSEEK_API_KEY"},
)


def _load_secret(ssm_name: str, env_key: str) -> None:
    load_ssm_secrets_if_needed(_SSM_SECRET_PREFIX, {ssm_name: env_key})


def get_bot_token() -> str:
    """Return Telegram bot token, loading SSM secrets on first use."""
    _load_secret("bot-token", "BOT_TOKEN")
    return require("BOT_TOKEN")


def get_webhook_secret_token() -> str:
    """Return Telegram webhook secret token, loading SSM secrets on first use."""
    _load_secret("webhook-secret-token", "WEBHOOK_SECRET_TOKEN")
    return require("WEBHOOK_SECRET_TOKEN")


def get_groq_api_key() -> str | None:
    """Return optional Groq API key, loading SSM secrets on first use."""
    _load_secret("groq-api-key", "GROQ_API_KEY")
    return os.environ.get("GROQ_API_KEY")


def get_gemini_api_key() -> str | None:
    """Return optional Gemini API key, loading SSM secrets on first use."""
    _load_secret("gemini-api-key", "GEMINI_API_KEY")
    return os.environ.get("GEMINI_API_KEY")


def get_deepseek_api_key() -> str | None:
    """Return optional DeepSeek API key, loading SSM secrets on first use."""
    _load_secret("deepseek-api-key", "DEEPSEEK_API_KEY")
    return os.environ.get("DEEPSEEK_API_KEY")


# ── Environment variables (non-secrets) ───────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
DEFAULT_LANG: str = os.environ.get("DEFAULT_LANG", "kk")

STATS_TABLE_NAME: str = require("STATS_TABLE_NAME")
QUEUE_URL: str = require("QUEUE_URL")

# ── Quiz parameters ─────────────────────────────────────────────────────────
QUIZ_TABLE_NAME: str | None = os.environ.get("QUIZ_TABLE_NAME")
QUIZ_LAMBDA_NAME: str | None = os.environ.get("QUIZ_LAMBDA_NAME")
ADMIN_USER_ID: int = require_int("ADMIN_USER_ID")

# ── Groq parameters ──────────────────────────────────────────────────────────
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL: str | None = os.environ.get("GROQ_MODEL")

# ── DeepSeek parameters ───────────────────────────────────────────────────────
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str | None = os.environ.get("DEEPSEEK_MODEL")

# ── Gemini parameters (non-key) ─────────────────────────────────────────────
GEMINI_API_BASE: str = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
WTF_GEMINI_MODEL: str | None = os.environ.get("WTF_GEMINI_MODEL")
GEMINI_RPD_LIMIT: int = require_int("GEMINI_RPD_LIMIT")

# ── Chat → language mapping ──────────────────────────────────────────────────
_CHAT_LANG_RAW: Any = require_json("CHAT_LANG_MAP")
if not isinstance(_CHAT_LANG_RAW, dict):
    raise ValueError("CHAT_LANG_MAP must be a JSON object (mapping of chat_id -> language code)")
CHAT_LANG_MAP: dict[str, str] = {str(k): str(v) for k, v in _CHAT_LANG_RAW.items()}


def get_chat_lang(chat_id: int | str | None) -> str:
    """Resolve the UI language for a chat from ``CHAT_LANG_MAP``, falling back to DEFAULT_LANG."""
    if chat_id is None:
        return DEFAULT_LANG
    return CHAT_LANG_MAP.get(str(chat_id), DEFAULT_LANG)


def is_configured_group_chat(chat_id: int | str | None) -> bool:
    """True when ``chat_id`` is allowed (present in the configured group → language map)."""
    if chat_id is None:
        return False
    return str(chat_id) in CHAT_LANG_MAP


# ── Timing parameters ──────────────────────────────────────────────────
CAPTCHA_TIMEOUT_SECONDS: int = require_int("CAPTCHA_TIMEOUT_SECONDS")
KICK_BAN_DURATION_SECONDS: int = require_int("KICK_BAN_DURATION_SECONDS")

# ── Vote-to-ban thresholds ──────────────────────────────────────────────────
VOTEBAN_THRESHOLD: int = require_int("VOTEBAN_THRESHOLD")
VOTEBAN_FORGIVE_THRESHOLD: int = require_int("VOTEBAN_FORGIVE_THRESHOLD")

# ── Captcha settings ────────────────────────────────────────────────────────
CAPTCHA_MAX_ATTEMPTS: int = require_int("CAPTCHA_MAX_ATTEMPTS")

# ── Callback-data prefixes ──────────────────────────────────────────────────
VOTEBAN_PREFIX = "voteban_"
VOTEBAN_FOR_PREFIX = "voteban_for_"
VOTEBAN_AGAINST_PREFIX = "voteban_against_"

# ── Telegram well-known ids ─────────────────────────────────────────────────
# ``from`` user id for messages posted via a channel into a linked discussion supergroup.
TELEGRAM_CHANNEL_POST_ACTOR_USER_ID: int = 777000

# ── Quiz parameters ─────────────────────────────────────────────────────────
VALID_LANGS = {"kk", "zh", "ru"}
VALID_DIFFICULTIES = {"easy", "medium", "hard", "expert"}


def __getattr__(name: str) -> str | None:
    """Lazily resolve API tokens / SSM-injected keys so cold start avoids boto3 until first use."""
    if name in _LAZY_SECRET_ATTRS:
        if name == "BOT_TOKEN":
            return get_bot_token()
        if name == "WEBHOOK_SECRET_TOKEN":
            return get_webhook_secret_token()
        if name == "GROQ_API_KEY":
            return get_groq_api_key()
        if name == "GEMINI_API_KEY":
            return get_gemini_api_key()
        if name == "DEEPSEEK_API_KEY":
            return get_deepseek_api_key()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(
        {*globals().keys(), *_LAZY_SECRET_ATTRS, "__dir__", "__getattr__"},
    )
