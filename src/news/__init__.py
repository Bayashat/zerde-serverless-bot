"""News Lambda package — re-exports config values for package-level imports."""

from config import AI_PROVIDER, BOT_TOKEN, NEWS_CHAT_IDS, get_groq_api_key

__all__ = ["BOT_TOKEN", "AI_PROVIDER", "NEWS_CHAT_IDS", "get_groq_api_key"]
