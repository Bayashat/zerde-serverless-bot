"""Centralised configuration: environment variables for the News Lambda."""

import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


# ── Required ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
NEWS_CHAT_IDS: list[str] = [cid.strip() for cid in _require("NEWS_CHAT_IDS").split(",") if cid.strip()]
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")

# ── Optional (have defaults) ─────────────────────────────────────────────────
AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "gemini")
LLM_MODEL: str = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
