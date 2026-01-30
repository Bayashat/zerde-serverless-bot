"""Worker Lambda package."""

import os

DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "kk")
TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET_TOKEN")

if not BOT_TOKEN or not WEBHOOK_SECRET_TOKEN:
    raise ValueError("BOT_TOKEN, WEBHOOK_SECRET_TOKEN must be set")

VERIFY_PREFIX = "verify_"
