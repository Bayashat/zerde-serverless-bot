"""Gemini REST API client for tech-term explanations.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups. The "day" matches
Gemini/Google: calendar date in America/Los_Angeles (midnight PT reset).

Timeout budget: explain tasks run via SQS Lambda (90 s budget), not API Gateway.
Plain-text explain: read timeout 25 s. Multimodal (large inline payloads): read 90 s.
"""

import base64
import json
import random
import time
from typing import Any

import urllib3
from core.config import GEMINI_API_BASE, WTF_GEMINI_MODEL, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from services.ai.explain_media_prompts import (
    document_summary_system_prompt,
    image_describe_system_prompt,
    transcribe_system_prompt,
)
from services.ai.wtf_prompts import WTFPromptStyle, get_wtf_system_prompt, wtf_explain_user_text
from services.repositories.rate_limit import RateLimitRepository
from urllib3.exceptions import HTTPError

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=25))
_http_multimodal = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=90))


def _thinking_config_for_model(model: str) -> dict[str, Any] | None:
    """Disable Gemini thinking for short plain-text explanations (latency > benefit)."""
    if model.startswith("gemini-2.5"):
        return {"thinkingBudget": 0}
    # gemini-3.x flash/flash-lite: thinking is off by default — no config needed.
    return None


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
        api_key = get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be set to initialize GeminiClient")
        self._api_key = api_key
        self._model = WTF_GEMINI_MODEL or "gemini-3.1-flash-lite-preview"
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

    def explain_term(self, term: str, lang: str = "kk", style: WTFPromptStyle = "angry") -> tuple[str, int]:
        """Call Gemini to explain *term*.

        Returns:
            (explanation_text, used_count_after_increment) so callers can build
            RPD footer without a second DynamoDB read.

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
        generation_config: dict[str, Any] = {
            "temperature": 0.7,
            "maxOutputTokens": 300,
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": "user", "parts": [{"text": wtf_explain_user_text(term)}]},
            ],
            "generationConfig": generation_config,
        }

        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        # Single retry for transient network/timeout failures. 503 (model globally
        # overloaded) breaks immediately — retrying in 1s won't help and just delays fallback.
        _retry_delays = (1,)
        last_exc: Exception | None = None

        logger.info(
            "Gemini explain request prepared",
            extra={
                "model": self._model,
                "lang": lang,
                "style": style,
                "temperature": generation_config["temperature"],
                "max_output_tokens": generation_config["maxOutputTokens"],
                "thinking_config": thinking_config,
                "rpd_count": count,
                "rpd_limit": self.rpd_limit,
                "term_chars": len(term),
            },
        )
        for attempt, delay in enumerate(_retry_delays):
            try:
                logger.info(
                    "Gemini explain request started",
                    extra={"model": self._model, "attempt": attempt + 1, "lang": lang, "style": style},
                )
                resp = _http.request("POST", url, body=body, headers=headers, retries=False)
            except (HTTPError, OSError) as exc:
                logger.warning(
                    "Gemini request failed (timeout / network)",
                    extra={"model": self._model, "attempt": attempt + 1, "error": str(exc)},
                )
                last_exc = GeminiUnavailableError(f"Gemini unreachable: {exc}")
                if attempt < len(_retry_delays) - 1:
                    time.sleep(delay + random.uniform(0, 2))
                continue

            if resp.status == 429:
                logger.warning("Gemini 429 rate limit", extra={"model": self._model})
                raise GeminiUnavailableError(f"Gemini 429: {resp.data.decode('utf-8')[:200]}")

            if resp.status in (500, 503, 504):
                body_text = resp.data.decode("utf-8")
                logger.warning(
                    "Gemini transient error, retrying",
                    extra={"status": resp.status, "attempt": attempt + 1, "body": body_text[:200]},
                )
                last_exc = GeminiUnavailableError(f"Gemini API {resp.status}: {body_text[:200]}")
                if resp.status == 503:
                    break  # globally overloaded — fall back immediately, don't retry
                if attempt < len(_retry_delays) - 1:
                    time.sleep(delay + random.uniform(0, 2))
                continue

            if resp.status >= 400:
                err_body = resp.data.decode("utf-8")
                logger.error("Gemini API error", extra={"status": resp.status, "body": err_body[:500]})
                raise GeminiUnavailableError(f"Gemini API {resp.status}: {err_body[:200]}")

            try:
                data = json.loads(resp.data.decode("utf-8"))
                candidate = data["candidates"][0]
                text = candidate["content"]["parts"][0]["text"].strip()
                logger.info(
                    "Gemini explain response parsed",
                    extra={
                        "model": self._model,
                        "attempt": attempt + 1,
                        "response_chars": len(text),
                        "finish_reason": candidate.get("finishReason"),
                        "rpd_count": count,
                        "rpd_limit": self.rpd_limit,
                    },
                )
                return text, count
            except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
                logger.exception(
                    "Gemini response parse error",
                    extra={"model": self._model, "attempt": attempt + 1, "status": resp.status},
                )
                raise GeminiUnavailableError(f"Bad Gemini response: {exc}") from exc

        raise last_exc or GeminiUnavailableError("Gemini unavailable after retries")

    def explain_media(
        self,
        *,
        media_kind: str,
        file_bytes: bytes,
        mime_type: str,
        lang: str,
        extra_user_text: str = "",
    ) -> tuple[str, int]:
        """Multimodal generateContent: voice/audio transcription, image Q&A, or document summary.

        Counts one RPD increment like ``explain_term``. No DeepSeek fallback at call-site.

        Raises:
            GeminiRPDExhaustedError, GeminiUnavailableError: same as ``explain_term``.
        """
        count, within_limit = self._rate_repo.increment_and_check()
        if not within_limit:
            logger.warning(
                "Gemini RPD limit reached (multimodal)",
                extra={"count": count, "limit": self.rpd_limit},
            )
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        if media_kind in ("voice", "audio"):
            system_prompt = transcribe_system_prompt(lang)
            max_output = 8192
            temperature = 0.2
        elif media_kind == "photo":
            system_prompt = image_describe_system_prompt(lang)
            max_output = 4096
            temperature = 0.4
        elif media_kind == "document":
            system_prompt = document_summary_system_prompt(lang)
            max_output = 8192
            temperature = 0.3
        else:
            raise ValueError(f"unsupported media_kind: {media_kind}")

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output,
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        b64 = base64.b64encode(file_bytes).decode("ascii")
        user_parts: list[dict[str, Any]] = []
        hint = (extra_user_text or "").strip()
        if hint:
            user_parts.append({"text": hint})
        user_parts.append({"inlineData": {"mimeType": mime_type, "data": b64}})

        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": user_parts}],
            "generationConfig": generation_config,
        }

        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}
        _retry_delays = (1,)
        last_exc: Exception | None = None

        logger.info(
            "Gemini multimodal request prepared",
            extra={
                "model": self._model,
                "lang": lang,
                "media_kind": media_kind,
                "mime_type": mime_type,
                "input_bytes": len(file_bytes),
                "rpd_count": count,
                "rpd_limit": self.rpd_limit,
            },
        )

        for attempt, delay in enumerate(_retry_delays):
            try:
                resp = _http_multimodal.request(
                    "POST",
                    url,
                    body=body,
                    headers=headers,
                    retries=False,
                )
            except (HTTPError, OSError) as exc:
                logger.warning(
                    "Gemini multimodal request failed (timeout / network)",
                    extra={"model": self._model, "attempt": attempt + 1, "error": str(exc)},
                )
                last_exc = GeminiUnavailableError(f"Gemini unreachable: {exc}")
                if attempt < len(_retry_delays) - 1:
                    time.sleep(delay + random.uniform(0, 2))
                continue

            if resp.status == 429:
                logger.warning("Gemini 429 rate limit (multimodal)", extra={"model": self._model})
                raise GeminiUnavailableError(f"Gemini 429: {resp.data.decode('utf-8')[:200]}")

            if resp.status in (500, 503, 504):
                body_text = resp.data.decode("utf-8")
                logger.warning(
                    "Gemini multimodal transient error",
                    extra={"status": resp.status, "attempt": attempt + 1, "body": body_text[:200]},
                )
                last_exc = GeminiUnavailableError(f"Gemini API {resp.status}: {body_text[:200]}")
                if resp.status == 503:
                    break
                if attempt < len(_retry_delays) - 1:
                    time.sleep(delay + random.uniform(0, 2))
                continue

            if resp.status >= 400:
                err_body = resp.data.decode("utf-8")
                logger.error(
                    "Gemini multimodal API error",
                    extra={"status": resp.status, "body": err_body[:500]},
                )
                raise GeminiUnavailableError(f"Gemini API {resp.status}: {err_body[:200]}")

            try:
                data = json.loads(resp.data.decode("utf-8"))
                candidate = data["candidates"][0]
                parts_out = candidate.get("content", {}).get("parts") or []
                text = ""
                for p in parts_out:
                    if isinstance(p, dict) and "text" in p:
                        text += str(p.get("text", ""))
                text = text.strip()
                if not text:
                    fr = candidate.get("finishReason", "")
                    raise GeminiUnavailableError(f"Empty multimodal response (finishReason={fr})")
                logger.info(
                    "Gemini multimodal response parsed",
                    extra={
                        "model": self._model,
                        "attempt": attempt + 1,
                        "response_chars": len(text),
                        "finish_reason": candidate.get("finishReason"),
                        "rpd_count": count,
                    },
                )
                return text, count
            except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
                logger.exception(
                    "Gemini multimodal response parse error",
                    extra={"model": self._model, "attempt": attempt + 1, "status": resp.status},
                )
                raise GeminiUnavailableError(f"Bad Gemini response: {exc}") from exc

        raise last_exc or GeminiUnavailableError("Gemini unavailable after retries")
