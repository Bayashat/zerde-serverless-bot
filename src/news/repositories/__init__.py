"""Repositories for news lambda."""

import os


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "groq")
GROQ_API_KEY: str = _require_env("GROQ_API_KEY")
