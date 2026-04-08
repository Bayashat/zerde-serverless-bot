"""Centralised configuration: environment variables for the News Lambda."""

import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


# ── Optional (have defaults) ─────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

AI_PROVIDER: str = os.environ.get("NEWS_AI_PROVIDER", "gemini")
LLM_MODEL: str = os.environ.get("NEWS_LLM_MODEL", "gemini-3-flash-preview")
FALLBACK_MODEL: str = os.environ.get("NEWS_FALLBACK_MODEL", "gemini-2.5-flash")


# ── Required ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
