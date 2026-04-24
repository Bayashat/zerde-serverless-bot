"""Centralised configuration: environment variables and constants."""

import json
import os

# ── SSM Secret Loading ──────────────────────────────────────────────────────
# When SSM_SECRET_PREFIX is set (Lambda), batch-fetch all secrets from
# Parameter Store and inject them into os.environ before any require() call.
# Falls back to plain env vars for local development (SSM_SECRET_PREFIX unset).
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")

if _SSM_SECRET_PREFIX:
    import boto3 as _boto3

    _ssm_env_map: dict[str, str] = {
        "bot-token": "BOT_TOKEN",
        "webhook-secret-token": "WEBHOOK_SECRET_TOKEN",
        "groq-api-key": "GROQ_API_KEY",
        "gemini-api-key": "GEMINI_API_KEY",
        "deepseek-api-key": "DEEPSEEK_API_KEY",
    }
    _ssm_response = _boto3.client("ssm").get_parameters(
        Names=[f"{_SSM_SECRET_PREFIX}/{k}" for k in _ssm_env_map],
        WithDecryption=True,
    )
    for _p in _ssm_response["Parameters"]:
        _k = _p["Name"].removeprefix(f"{_SSM_SECRET_PREFIX}/")
        if _env_key := _ssm_env_map.get(_k):
            os.environ[_env_key] = _p["Value"]

# ── Environment variables ───────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
DEFAULT_LANG: str = os.environ.get("DEFAULT_LANG", "kk")


def require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"{key} must be set")
    return value


BOT_TOKEN: str = require("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN: str = require("WEBHOOK_SECRET_TOKEN")
STATS_TABLE_NAME: str = require("STATS_TABLE_NAME")
QUEUE_URL: str = require("QUEUE_URL")

# ── Quiz parameters ─────────────────────────────────────────────────────────
QUIZ_TABLE_NAME: str = os.environ.get("QUIZ_TABLE_NAME")
QUIZ_LAMBDA_NAME: str = os.environ.get("QUIZ_LAMBDA_NAME")
ADMIN_USER_ID: int = int(os.environ.get("ADMIN_USER_ID"))

# ── Groq parameters ──────────────────────────────────────────────────────────
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL")

# ── DeepSeek parameters ───────────────────────────────────────────────────────
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL")


# ── Gemini parameters ──────────────────────────────────────────────────────────
GEMINI_API_BASE: str = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY")
WTF_GEMINI_MODEL: str = os.environ.get("WTF_GEMINI_MODEL")
GEMINI_RPD_LIMIT: int = int(os.environ.get("GEMINI_RPD_LIMIT"))

# ── Chat → language mapping ──────────────────────────────────────────────────
CHAT_LANG_MAP: dict[str, str] = json.loads(os.environ.get("CHAT_LANG_MAP"))


def get_chat_lang(chat_id: int | str | None) -> str:
    """Resolve the UI language for a chat from ``CHAT_LANG_MAP``, falling back to DEFAULT_LANG."""
    if chat_id is None:
        return DEFAULT_LANG
    return CHAT_LANG_MAP.get(str(chat_id), DEFAULT_LANG)


# ── Timing parameters ──────────────────────────────────────────────────
CAPTCHA_TIMEOUT_SECONDS = int(os.environ.get("CAPTCHA_TIMEOUT_SECONDS"))
KICK_BAN_DURATION_SECONDS = int(os.environ.get("KICK_BAN_DURATION_SECONDS"))


# ── Vote-to-ban thresholds ──────────────────────────────────────────────────
VOTEBAN_THRESHOLD = int(os.environ.get("VOTEBAN_THRESHOLD"))
VOTEBAN_FORGIVE_THRESHOLD = int(os.environ.get("VOTEBAN_FORGIVE_THRESHOLD"))


# ── Captcha settings ────────────────────────────────────────────────────────
CAPTCHA_MAX_ATTEMPTS: int = int(os.environ.get("CAPTCHA_MAX_ATTEMPTS"))

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
