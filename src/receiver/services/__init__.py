"""Receiver Lambda package."""

import os

WEBHOOK_SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET_TOKEN")

if not WEBHOOK_SECRET_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN and WEBHOOK_SECRET_TOKEN must be set")
