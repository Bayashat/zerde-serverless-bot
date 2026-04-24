"""Centralised configuration: environment variables for the News Lambda."""

import os

# ── SSM Secret Loading ──────────────────────────────────────────────────────
_SSM_SECRET_PREFIX: str = os.environ.get("SSM_SECRET_PREFIX", "")

if _SSM_SECRET_PREFIX:
    import boto3 as _boto3

    _ssm_env_map: dict[str, str] = {
        "bot-token": "BOT_TOKEN",
        "gemini-api-key": "GEMINI_API_KEY",
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


# ── Optional (have defaults) ─────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

AI_PROVIDER: str = os.environ.get("NEWS_AI_PROVIDER", "gemini")
LLM_MODEL: str = os.environ.get("NEWS_GEMINI_MODEL", "gemini-3-flash-preview")
FALLBACK_MODEL: str = os.environ.get("NEWS_FALLBACK_MODEL", "gemini-2.5-flash")


# ── Required ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = _require("BOT_TOKEN")
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")
