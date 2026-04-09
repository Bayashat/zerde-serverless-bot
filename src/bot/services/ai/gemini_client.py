"""Gemini REST API client for tech-term explanations.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups. The "day" matches
Gemini/Google: calendar date in America/Los_Angeles (midnight PT reset).

Timeout budget: API Gateway HTTP API hard-limits responses to 30 s.
Gemini (12 s) + possible DeepSeek/Llama fallback (15 s) + overhead ≈ 26 s.
"""

import json
from typing import Any

import urllib3
from core.config import GEMINI_API_BASE, GEMINI_API_KEY, WTF_GEMINI_MODEL
from core.logger import LoggerAdapter, get_logger
from services.ai.wtf_prompts import WTFPromptStyle, get_wtf_system_prompt, wtf_explain_user_text
from services.repositories.rate_limit import RateLimitRepository
from urllib3.exceptions import HTTPError

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=20))


class GeminiRPDExhaustedError(Exception):
    """Daily RPD quota is exhausted (DynamoDB counter over limit)."""


class GeminiUnavailableError(Exception):
    """Transient Gemini failure: HTTP 429/5xx, timeout, network, parse errors.

    Callers should fall back to the configured OpenAI-compatible provider *without*
    the daily-quota user notice.
    """


class GeminiClient:
    """Thin urllib3 wrapper around the Gemini generateContent REST endpoint."""

    def __init__(self) -> None:
        self._api_key = GEMINI_API_KEY
        self._model = WTF_GEMINI_MODEL
        self._rate_repo = RateLimitRepository()
        logger.info("GeminiClient initialized", extra={"model": self._model})

    @property
    def remaining_rpd(self) -> int:
        """Remaining Gemini calls today before hitting RPD limit (read from DynamoDB)."""
        used = self._rate_repo.get_today_count()
        return max(0, self._rate_repo.rpd_limit - used)

    @property
    def rpd_limit(self) -> int:
        return self._rate_repo.rpd_limit

    def explain_term(self, term: str, lang: str = "kk", style: WTFPromptStyle = "angry") -> str:
        """Call Gemini to explain *term*.

        Raises:
            GeminiRPDExhaustedError: daily RPD limit reached after increment.
            GeminiUnavailableError: 429, 5xx, timeout, or bad response body.
        """
        count, within_limit = self._rate_repo.increment_and_check()

        if not within_limit:
            logger.warning(
                "Gemini RPD limit reached",
                extra={"count": count, "limit": self.rpd_limit},
            )
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        system_prompt = get_wtf_system_prompt(lang, style)
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": wtf_explain_user_text(term)}]},
            ],
            "generationConfig": {
                "temperature": 0.9,
                "maxOutputTokens": 400,
            },
        }

        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"

        try:
            resp = _http.request(
                "POST",
                url,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                retries=False,
            )
        except (HTTPError, OSError) as exc:
            logger.warning(
                "Gemini request failed (timeout / network)",
                extra={"model": self._model, "error": str(exc)},
            )
            raise GeminiUnavailableError(f"Gemini unreachable: {exc}") from exc

        if resp.status == 429:
            logger.warning("Gemini 429 rate limit", extra={"model": self._model})
            raise GeminiUnavailableError(f"Gemini 429: {resp.data.decode('utf-8')[:200]}")

        if resp.status >= 400:
            body = resp.data.decode("utf-8")
            logger.error(
                "Gemini API error",
                extra={"status": resp.status, "body": body[:500]},
            )
            raise GeminiUnavailableError(f"Gemini API {resp.status}: {body[:200]}")

        try:
            data = json.loads(resp.data.decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            logger.exception("Gemini response parse error")
            raise GeminiUnavailableError(f"Bad Gemini response: {exc}") from exc
