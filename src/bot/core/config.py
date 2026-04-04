"""Centralised configuration: environment variables and constants."""

import os

# ── Environment variables ───────────────────────────────────────────────────
BOT_TOKEN: str = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN: str = os.environ.get("WEBHOOK_SECRET_TOKEN")
QUEUE_URL: str = os.environ.get("QUEUE_URL")
STATS_TABLE_NAME: str = os.environ.get("STATS_TABLE_NAME")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
DEFAULT_LANG: str = os.environ.get("DEFAULT_LANG", "kk")


def require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"{key} must be set")
    return value


BOT_TOKEN = require("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = require("WEBHOOK_SECRET_TOKEN")
STATS_TABLE_NAME = require("STATS_TABLE_NAME")
QUEUE_URL = require("QUEUE_URL")


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
