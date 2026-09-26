"""Centralised configuration: environment variables and constants."""

import json
import os
from typing import Any

from zerde_common.config import require, require_int, require_json
from zerde_common.secrets import load_ssm_secrets_if_needed

# Secrets are loaded only by the accessors below.  This keeps workers such as
# the vector indexer from needing permission to read unrelated bot secrets.
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")
_LAZY_SECRET_ATTRS: frozenset[str] = frozenset(
    {
        "BOT_TOKEN",
        "WEBHOOK_SECRET_TOKEN",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
    }
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


def get_deepseek_api_key() -> str | None:
    """Return optional DeepSeek API key, loading SSM secrets on first use."""
    _load_secret("deepseek-api-key", "DEEPSEEK_API_KEY")
    return os.environ.get("DEEPSEEK_API_KEY")


def get_gemini_api_key() -> str | None:
    """Return optional Gemini API key, loading SSM secrets on first use."""
    _load_secret("gemini-api-key", "GEMINI_API_KEY")
    return os.environ.get("GEMINI_API_KEY")


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
GROQ_SPAM_MODEL: str = os.environ.get("GROQ_SPAM_MODEL", "openai/gpt-oss-safeguard-20b")

# ── DeepSeek fallback parameters ───────────────────────────────────────────
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

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


def _env_optional_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    value = os.environ.get(name)
    if value is None:
        value = default
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _env_json_object(name: str, default: str = "{}") -> dict[str, Any]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        raw = default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


_SPAM_REVIEW_ADMIN_MENTIONS_RAW: dict[str, Any] = _env_json_object("SPAM_REVIEW_ADMIN_MENTIONS", "{}")
SPAM_REVIEW_ADMIN_MENTIONS: dict[str, tuple[str, ...]] = {
    str(chat_id): tuple(
        username.strip().lstrip("@") for username in usernames if isinstance(username, str) and username.strip()
    )
    for chat_id, usernames in _SPAM_REVIEW_ADMIN_MENTIONS_RAW.items()
    if isinstance(usernames, list)
}


def get_spam_review_admin_mentions(chat_id: int | str | None) -> tuple[str, ...]:
    """Return configured usernames to notify for a chat's uncertain spam review alerts."""
    if chat_id is None:
        return ()
    return SPAM_REVIEW_ADMIN_MENTIONS.get(str(chat_id), ())


def is_configured_group_chat(chat_id: int | str | None) -> bool:
    """True when ``chat_id`` is allowed (present in the configured group → language map)."""
    if chat_id is None:
        return False
    return str(chat_id) in CHAT_LANG_MAP


# ── Timing parameters ──────────────────────────────────────────────────
CAPTCHA_TIMEOUT_SECONDS: int = require_int("CAPTCHA_TIMEOUT_SECONDS")
KICK_BAN_CONFIGURED_DURATION_SECONDS: int = int(os.environ.get("KICK_BAN_DURATION_SECONDS", "60"))
# Telegram interprets a deadline <30 seconds away as permanent; allow transport margin.
KICK_BAN_DURATION_SECONDS: int = max(60, KICK_BAN_CONFIGURED_DURATION_SECONDS)

# ── Vote-to-ban thresholds ──────────────────────────────────────────────────
VOTEBAN_THRESHOLD: int = require_int("VOTEBAN_THRESHOLD")
VOTEBAN_FORGIVE_THRESHOLD: int = require_int("VOTEBAN_FORGIVE_THRESHOLD")

# ── Captcha settings ────────────────────────────────────────────────────────
CAPTCHA_MAX_ATTEMPTS: int = require_int("CAPTCHA_MAX_ATTEMPTS")


# ── Group memory / agent MVP ────────────────────────────────────────────────


# Generated by CDK; current V2 storage never falls back to another table.
MEMORY_V2_TABLE_NAME: str | None = os.environ.get("MEMORY_V2_TABLE_NAME")
AGENT_BOT_USERNAME: str = os.environ.get("AGENT_BOT_USERNAME", "").lstrip("@").lower()
AGENT_BOT_ID: int | None = _env_optional_int("AGENT_BOT_ID")
MULTIMODAL_ENABLED: bool = _env_bool("MULTIMODAL_ENABLED", True)
MULTIMODAL_MAX_DOWNLOAD_BYTES: int = int(os.environ.get("MULTIMODAL_MAX_DOWNLOAD_BYTES", "12000000"))
MULTIMODAL_INLINE_MAX_BYTES: int = int(os.environ.get("MULTIMODAL_INLINE_MAX_BYTES", "8000000"))
MULTIMODAL_TEXT_FILE_MAX_CHARS: int = int(os.environ.get("MULTIMODAL_TEXT_FILE_MAX_CHARS", "20000"))


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
        if name == "DEEPSEEK_API_KEY":
            return get_deepseek_api_key()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:  # pragma: no cover
    return sorted(
        {*globals().keys(), *_LAZY_SECRET_ATTRS, "__dir__", "__getattr__"},
    )
