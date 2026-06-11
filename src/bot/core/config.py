"""Centralised configuration: environment variables and constants."""

import os
from typing import Any

from zerde_common.config import require, require_int, require_json
from zerde_common.secrets import load_ssm_secrets_if_needed

# ── SSM: one GetParameters batch at import when SSM_SECRET_PREFIX is set (warm path avoids SSM). ─
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")
_SSM_KEY_MAP: dict[str, str] = {
    "bot-token": "BOT_TOKEN",
    "webhook-secret-token": "WEBHOOK_SECRET_TOKEN",
    "groq-api-key": "GROQ_API_KEY",
    "gemini-api-key": "GEMINI_API_KEY",
}
if _SSM_SECRET_PREFIX:
    load_ssm_secrets_if_needed(_SSM_SECRET_PREFIX, _SSM_KEY_MAP)
_LAZY_SECRET_ATTRS: frozenset[str] = frozenset({"BOT_TOKEN", "WEBHOOK_SECRET_TOKEN", "GROQ_API_KEY", "GEMINI_API_KEY"})


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


def get_gemini_embedding_api_key() -> str | None:
    """Return an optional embeddings-only Gemini key, falling back to the main Gemini key."""
    if os.environ.get("GEMINI_EMBEDDING_API_KEY"):
        return os.environ.get("GEMINI_EMBEDDING_API_KEY")
    if _SSM_SECRET_PREFIX:
        try:
            load_ssm_secrets_if_needed(
                _SSM_SECRET_PREFIX,
                {"gemini-embedding-api-key": "GEMINI_EMBEDDING_API_KEY"},
            )
        except Exception as exc:
            if "gemini-embedding-api-key" not in str(exc):
                raise
    return os.environ.get("GEMINI_EMBEDDING_API_KEY") or get_gemini_api_key()


# ── Environment variables (non-secrets) ───────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
DEFAULT_LANG: str = os.environ.get("DEFAULT_LANG", "kk")

STATS_TABLE_NAME: str = require("STATS_TABLE_NAME")
QUEUE_URL: str = require("QUEUE_URL")
VECTOR_MEMORY_QUEUE_URL: str | None = os.environ.get("VECTOR_MEMORY_QUEUE_URL")

# ── Quiz parameters ─────────────────────────────────────────────────────────
QUIZ_TABLE_NAME: str | None = os.environ.get("QUIZ_TABLE_NAME")
QUIZ_LAMBDA_NAME: str | None = os.environ.get("QUIZ_LAMBDA_NAME")
ADMIN_USER_ID: int = require_int("ADMIN_USER_ID")

# ── Groq parameters ──────────────────────────────────────────────────────────
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL: str | None = os.environ.get("GROQ_MODEL")

# ── Spam moderation thresholds ──────────────────────────────────────────────
SPAM_RULE_ENFORCE_THRESHOLD: float = float(os.environ.get("SPAM_RULE_ENFORCE_THRESHOLD", "0.8"))
SPAM_RULE_AI_THRESHOLD: float = float(os.environ.get("SPAM_RULE_AI_THRESHOLD", "0.15"))
SPAM_AI_CONFIDENCE_THRESHOLD: float = float(os.environ.get("SPAM_AI_CONFIDENCE_THRESHOLD", "0.85"))

# ── Gemini parameters (non-key) ─────────────────────────────────────────────
GEMINI_API_BASE: str = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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

# ── Group memory / agent MVP ────────────────────────────────────────────────
MEMORY_TABLE_NAME: str | None = os.environ.get("MEMORY_TABLE_NAME")
GROUP_MEMORY_ENABLED: bool = _env_bool("GROUP_MEMORY_ENABLED", True)
GROUP_MEMORY_RECENT_LIMIT: int = int(os.environ.get("GROUP_MEMORY_RECENT_LIMIT", "80"))
GROUP_MEMORY_RETENTION_DAYS: int = int(os.environ.get("GROUP_MEMORY_RETENTION_DAYS", "3650"))
AGENT_ENABLED: bool = _env_bool("AGENT_ENABLED", True)
AGENT_BOT_USERNAME: str = os.environ.get("AGENT_BOT_USERNAME", "").lstrip("@").lower()
AGENT_RECENT_CONTEXT_LIMIT: int = int(os.environ.get("AGENT_RECENT_CONTEXT_LIMIT", "40"))
AGENT_DAILY_PROACTIVE_LIMIT: int = int(os.environ.get("AGENT_DAILY_PROACTIVE_LIMIT", "3"))
AGENT_PROACTIVE_SCORE_THRESHOLD: float = float(os.environ.get("AGENT_PROACTIVE_SCORE_THRESHOLD", "0.62"))
AGENT_PROACTIVE_FINAL_THRESHOLD: float = float(os.environ.get("AGENT_PROACTIVE_FINAL_THRESHOLD", "0.72"))
GROUP_MEMORY_DAILY_SUMMARY_DAYS: int = int(os.environ.get("GROUP_MEMORY_DAILY_SUMMARY_DAYS", "7"))
GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT: int = int(os.environ.get("GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT", "500"))

# ── Vector memory retrieval ────────────────────────────────────────────────
VECTOR_MEMORY_ENABLED: bool = _env_bool("VECTOR_MEMORY_ENABLED", True)
VECTOR_MEMORY_PROVIDER: str = os.environ.get("VECTOR_MEMORY_PROVIDER", "s3_vectors").strip().lower()
VECTOR_MEMORY_VECTOR_BUCKET_NAME: str | None = os.environ.get("VECTOR_MEMORY_VECTOR_BUCKET_NAME")
VECTOR_MEMORY_INDEX_NAME: str | None = os.environ.get("VECTOR_MEMORY_INDEX_NAME")
VECTOR_MEMORY_DIMENSIONS: int = int(os.environ.get("VECTOR_MEMORY_DIMENSIONS", "768"))
VECTOR_MEMORY_EMBEDDING_MODEL: str = os.environ.get("VECTOR_MEMORY_EMBEDDING_MODEL", "gemini-embedding-2")
VECTOR_MEMORY_BACKFILL_BATCH_SIZE: int = int(os.environ.get("VECTOR_MEMORY_BACKFILL_BATCH_SIZE", "50"))
VECTOR_MEMORY_INDEX_THROTTLE_SECONDS: float = float(os.environ.get("VECTOR_MEMORY_INDEX_THROTTLE_SECONDS", "0"))

# ── Callback-data prefixes ──────────────────────────────────────────────────
VOTEBAN_PREFIX = "voteban_"
VOTEBAN_FOR_PREFIX = "voteban_for_"
VOTEBAN_AGAINST_PREFIX = "voteban_against_"
SPAM_REVIEW_BAN_PREFIX = "spam_ban:"
SPAM_REVIEW_IGNORE_PREFIX = "spam_ignore:"

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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(
        {*globals().keys(), *_LAZY_SECRET_ATTRS, "__dir__", "__getattr__"},
    )
