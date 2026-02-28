"""Repositories for news lambda."""

import os

AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "gemini")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "").strip()
LLM_MODEL: str = os.environ.get("LLM_MODEL", "gemini-3-flash-preview")
