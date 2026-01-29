import os

STAT_KEY_GLOBAL = "global_stats"

QUEUE_URL = os.environ.get("QUEUE_URL")
STATS_TABLE_NAME = os.environ.get("STATS_TABLE_NAME")
TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not STATS_TABLE_NAME or not BOT_TOKEN:
    raise ValueError("STATS_TABLE_NAME and BOT_TOKEN must be set")
if not QUEUE_URL:
    raise ValueError("QUEUE_URL must be set")
