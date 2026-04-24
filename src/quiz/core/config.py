# src/quiz/core/config.py
"""Centralised configuration: environment variables for the Quiz Lambda."""

import os

# ── SSM Secret Loading ──────────────────────────────────────────────────────
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")

if _SSM_SECRET_PREFIX:
    import boto3 as _boto3

    _ssm_env_map: dict[str, str] = {
        "bot-token": "BOT_TOKEN",
        "gemini-api-key": "GEMINI_API_KEY",
        "groq-api-key": "GROQ_API_KEY",
    }
    _ssm_response = _boto3.client("ssm").get_parameters(
        Names=[f"{_SSM_SECRET_PREFIX}/{k}" for k in _ssm_env_map],
        WithDecryption=True,
    )
    for _p in _ssm_response["Parameters"]:
        _k = _p["Name"].removeprefix(f"{_SSM_SECRET_PREFIX}/")
        if _env_key := _ssm_env_map.get(_k):
            os.environ[_env_key] = _p["Value"]


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
