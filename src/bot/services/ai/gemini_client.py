"""Gemini REST API client for tech-term explanations.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups.
"""

import json
from typing import Any

import urllib3
from core.config import GEMINI_API_KEY, GEMINI_MODEL
from core.logger import LoggerAdapter, get_logger
from services.ai.groq_client import DEFAULT_SYSTEM_PROMPT, SYSTEM_PROMPTS
from services.repositories.rate_limit import RateLimitRepository

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=20))

_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiRateLimitError(Exception):
    """Raised when Gemini returns HTTP 429 or RPD limit is reached."""


class GeminiClient:
    """Thin urllib3 wrapper around the Gemini generateContent REST endpoint."""

    def __init__(self) -> None:
        self._api_key = GEMINI_API_KEY
        self._model = GEMINI_MODEL
        self._rate_repo = RateLimitRepository()
        self._last_count = 0
        logger.info("GeminiClient initialized", extra={"model": self._model})

    @property
    def remaining_rpd(self) -> int:
        return max(0, self._rate_repo.rpd_limit - self._last_count)

    @property
    def rpd_limit(self) -> int:
        return self._rate_repo.rpd_limit

    def explain_term(self, term: str, lang: str = "kk") -> str:
        """Call Gemini to explain *term*.

        Raises GeminiRateLimitError when the shared RPD counter
        exceeds the limit or the API returns 429.
        """
        count, within_limit = self._rate_repo.increment_and_check()
        self._last_count = count

        if not within_limit:
            logger.warning(
                "Gemini RPD limit reached",
                extra={"count": count, "limit": self.rpd_limit},
            )
            raise GeminiRateLimitError(f"RPD limit reached: {count}/{self.rpd_limit}")

        system_prompt = SYSTEM_PROMPTS.get(lang, DEFAULT_SYSTEM_PROMPT)
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": f"Explain the term: {term}"}]},
            ],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 400,
            },
        }

        url = f"{_GEMINI_API_URL}/{self._model}:generateContent?key={self._api_key}"
        resp = _http.request(
            "POST",
            url,
            body=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )

        if resp.status == 429:
            logger.warning("Gemini 429 rate limit", extra={"model": self._model})
            raise GeminiRateLimitError(f"Gemini 429: {resp.data.decode('utf-8')[:200]}")

        if resp.status >= 400:
            body = resp.data.decode("utf-8")
            logger.error(
                "Gemini API error",
                extra={"status": resp.status, "body": body[:500]},
            )
            raise RuntimeError(f"Gemini API {resp.status}: {body[:200]}")

        data = json.loads(resp.data.decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
