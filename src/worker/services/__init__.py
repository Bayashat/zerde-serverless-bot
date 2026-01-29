"""Receiver Lambda package."""

import os

DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "en")
TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET_TOKEN")

if not BOT_TOKEN or not WEBHOOK_SECRET_TOKEN:
    raise ValueError("BOT_TOKEN, WEBHOOK_SECRET_TOKEN must be set")

BOT_NAME = os.environ.get("BOT_NAME", "Example Bot")
BOT_DESCRIPTION = os.environ.get("BOT_DESCRIPTION", "Example Bot Description")
BOT_INSTRUCTIONS = os.environ.get("BOT_INSTRUCTIONS", "Example Bot Instructions")

# Inline keyboard callback prefix for verification
VERIFY_PREFIX = "verify_"
