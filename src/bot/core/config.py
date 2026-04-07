"""Centralised configuration: environment variables and constants."""

import json
import os

# ── Environment variables ───────────────────────────────────────────────────
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
QUIZ_TABLE_NAME: str = os.environ.get("QUIZ_TABLE_NAME", "")
QUIZ_LAMBDA_NAME: str = os.environ.get("QUIZ_LAMBDA_NAME", "")
ADMIN_USER_ID: int = int(os.environ.get("ADMIN_USER_ID", "0"))

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

LLAMA_API_KEY: str = os.environ.get("LLAMA_API_KEY", "")
LLAMA_API_BASE: str = os.environ.get("LLAMA_API_BASE", "https://api.llama.com/compat/v1")
LLAMA_MODEL: str = os.environ.get("LLAMA_MODEL", "Llama-4-Maverick-17B-128E-Instruct-FP8")

DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE: str = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# Which provider to use as Gemini fallback: "deepseek" | "llama"
WTF_FALLBACK_PROVIDER: str = os.environ.get("WTF_FALLBACK_PROVIDER", "deepseek")

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
GEMINI_RPD_LIMIT: int = int(os.environ.get("GEMINI_RPD_LIMIT", "500"))


# ── Callback-data prefixes ──────────────────────────────────────────────────
VERIFY_PREFIX = "verify_"
VOTEBAN_PREFIX = "voteban_"
VOTEBAN_FOR_PREFIX = "voteban_for_"
VOTEBAN_AGAINST_PREFIX = "voteban_against_"

# ── Captcha / kick timing ───────────────────────────────────────────────────
CAPTCHA_TIMEOUT_SECONDS = 60
KICK_BAN_DURATION_SECONDS = 31

# ── Vote-to-ban thresholds ──────────────────────────────────────────────────
VOTEBAN_THRESHOLD = 7
VOTEBAN_FORGIVE_THRESHOLD = 7

# ── Chat → language mapping ──────────────────────────────────────────────────
CHAT_LANG_MAP: dict[str, str] = json.loads(os.environ.get("CHAT_LANG_MAP", "{}"))


def get_chat_lang(chat_id: int | str) -> str:
    """Resolve the language for a chat, falling back to DEFAULT_LANG."""
    return CHAT_LANG_MAP.get(str(chat_id), DEFAULT_LANG)


# ── Quiz parameters ─────────────────────────────────────────────────────────
VALID_LANGS = {"kk", "zh", "ru"}
VALID_DIFFICULTIES = {"easy", "medium", "hard", "expert"}
