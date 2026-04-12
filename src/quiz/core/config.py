# src/quiz/core/config.py
"""Centralised configuration: environment variables for the Quiz Lambda."""

import os


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


# ── Optional ────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TELEGRAM_API_BASE: str = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "gemini")
GEMINI_MODEL: str = os.environ.get("QUIZ_GEMINI_MODEL", "gemini-2.5-flash-lite")
QUIZ_LLM_RPD: int = int(os.environ.get("QUIZ_LLM_RPD", "20"))


# ── Required ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
TABLE_NAME: str = _require("TABLE_NAME")
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")

# ── Groq fallback ───────────────────────────────────────────────────────────
GROQ_API_BASE: str = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
