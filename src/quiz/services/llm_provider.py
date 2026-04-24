"""LLM provider abstraction with Gemini primary and DeepSeek fallback."""

import json
import random
import time
from abc import ABC, abstractmethod
from typing import Any, TypedDict

import urllib3
from core.config import DEEPSEEK_API_BASE, DEEPSEEK_MODEL, GEMINI_MODEL, get_deepseek_api_key, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from services.rate_limit_repository import QuizRateLimitRepository
from zerde_common.ai_errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.logging_utils import llm_text_log_fields

logger = LoggerAdapter(get_logger(__name__), {})


class _QuizQuestionResponse(TypedDict):
    question: str
    options: list[str]
    correct_option_index: int
    explanation: str


def _map_gemini_api_error(exc: genai_errors.APIError) -> ZerdeProviderError:
    if exc.code == 429:
        return ProviderRateLimitError(str(exc))
    if exc.code in (500, 503, 504):
        return ProviderTransportError(str(exc))
    if exc.code and 400 <= int(exc.code) < 500:
        return ProviderResponseError(str(exc))
    return ProviderResponseError(str(exc))


class RateLimitError(ProviderRateLimitError):
    """Back-compat: local RPD limit or upstream 429."""


class QuizLLMProvider(ABC):
    """Abstract interface for quiz JSON generation."""

    @abstractmethod
    def generate_json(self, prompt: str, temperature: float = 0.3) -> dict:
        """Send *prompt* and return the parsed JSON dict.

        Raises:
            RateLimitError: when the provider's rate limit is exceeded.
            Exception: on any other provider failure.
        """

    def get_rpd_status(self) -> tuple[int | None, int | None]:
        """Return remaining/total RPD when provider tracks it, else ``(None, None)``."""
        return None, None


class GeminiQuizProvider(QuizLLMProvider):
    """Google Gemini provider via google-genai SDK."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._rate_repo = QuizRateLimitRepository()
        logger.info("GeminiQuizProvider initialized", extra={"model": model})

    def get_rpd_status(self) -> tuple[int, int]:
        used = self._rate_repo.get_today_count()
        total = self._rate_repo.rpd_limit
        remaining = max(0, total - used)
        return remaining, total

    _RETRY_DELAYS = (5, 15, 30)  # seconds; quiz runs on schedule, has time

    def generate_json(self, prompt: str, temperature: float = 0.3) -> dict:
        count, within_limit = self._rate_repo.increment_and_check()
        if not within_limit:
            logger.warning(
                "Quiz Gemini RPD limit reached",
                extra={"count": count, "limit": self._rate_repo.rpd_limit, "model": self._model},
            )
            raise RateLimitError(f"Quiz Gemini RPD limit reached: {count}/{self._rate_repo.rpd_limit}")

        for attempt, delay in enumerate(self._RETRY_DELAYS):
            try:
                logger.info(
                    "Quiz Gemini request started",
                    extra={
                        "model": self._model,
                        "attempt": attempt + 1,
                        "temperature": temperature,
                        "response_schema": _QuizQuestionResponse.__name__,
                        "rpd_count": count,
                        "rpd_limit": self._rate_repo.rpd_limit,
                    },
                )
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=temperature,
                        response_mime_type="application/json",
                        response_schema=_QuizQuestionResponse,
                        max_output_tokens=2000,
                    ),
                )
                text = response.text.strip()
                logger.debug("Quiz LLM response (preview)", extra=llm_text_log_fields(text))
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as je:
                    raise ProviderResponseError(f"Gemini returned invalid JSON: {je}") from je
                logger.info(
                    "Quiz Gemini response parsed",
                    extra={"model": self._model, "attempt": attempt + 1, "response_chars": len(text)},
                )
                return data
            except genai_errors.APIError as exc:
                if exc.code == 429:
                    logger.warning("Gemini 429 rate limit hit", extra={"model": self._model})
                    raise ProviderRateLimitError(str(exc)) from exc
                retryable = exc.code in (500, 503, 504)
                is_last_attempt = attempt == len(self._RETRY_DELAYS) - 1
                if not retryable or is_last_attempt:
                    raise _map_gemini_api_error(exc) from exc
                wait = delay + random.uniform(0, 3)
                logger.warning(
                    "Quiz Gemini request failed, retrying with backoff",
                    extra={"attempt": attempt + 1, "wait_s": round(wait, 1), "code": exc.code},
                )
                time.sleep(wait)
            except ZerdeProviderError:
                raise


class DeepSeekQuizProvider(QuizLLMProvider):
    """DeepSeek provider via OpenAI-compatible chat/completions endpoint."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=5, read=60))

    def __init__(self, api_key: str, api_base: str, model: str) -> None:
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info("DeepSeekQuizProvider initialized", extra={"model": model})

    def generate_json(self, prompt: str, temperature: float = 0.3) -> dict:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "Quiz DeepSeek request started",
            extra={"model": self._model, "temperature": temperature, "response_format": "json_object"},
        )
        resp = self._http.request(
            "POST",
            f"{self._api_base}/chat/completions",
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        if resp.status == 429:
            logger.warning("DeepSeek 429 rate limit hit", extra={"model": self._model})
            raise ProviderRateLimitError(f"DeepSeek rate limited: {resp.status}")

        if resp.status >= 400:
            body = resp.data.decode("utf-8")
            logger.error("DeepSeek API error", extra={"status": resp.status, "body": body[:500]})
            raise map_http_status_to_provider_error(
                resp.status,
                f"DeepSeek API {resp.status}: {body[:200]}",
            )

        try:
            data = json.loads(resp.data.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except json.JSONDecodeError as e:
            raise ProviderResponseError(f"DeepSeek response was not valid JSON: {e}") from e
        except (KeyError, IndexError, TypeError):
            raise
        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            raise ProviderResponseError(f"DeepSeek returned invalid content JSON: {e}") from e
        logger.info(
            "Quiz DeepSeek response parsed",
            extra={"model": self._model, "response_chars": len(content)},
        )
        return result


class FallbackProvider(QuizLLMProvider):
    """Tries the primary provider; on ``ZerdeProviderError`` uses the secondary."""

    def __init__(self, primary: QuizLLMProvider, fallback: QuizLLMProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def generate_json(self, prompt: str, temperature: float = 0.3) -> dict:
        try:
            result = self._primary.generate_json(prompt, temperature)
            logger.info("Quiz generated by primary provider")
            return result
        except ZerdeProviderError as e:
            logger.warning(
                "Primary provider failed, falling back to secondary provider",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            result = self._fallback.generate_json(prompt, temperature)
            logger.info("Quiz generated by fallback provider")
            return result

    def get_rpd_status(self) -> tuple[int | None, int | None]:
        return self._primary.get_rpd_status()


def create_provider() -> QuizLLMProvider:
    """Build the provider chain: Gemini primary -> DeepSeek fallback (if configured)."""
    primary: QuizLLMProvider = GeminiQuizProvider(api_key=get_gemini_api_key(), model=GEMINI_MODEL)

    deepseek_api_key = get_deepseek_api_key()
    if deepseek_api_key:
        fallback = DeepSeekQuizProvider(api_key=deepseek_api_key, api_base=DEEPSEEK_API_BASE, model=DEEPSEEK_MODEL)
        logger.info(
            "FallbackProvider configured",
            extra={"primary": GEMINI_MODEL, "fallback": DEEPSEEK_MODEL},
        )
        return FallbackProvider(primary=primary, fallback=fallback)

    logger.info("DeepSeek fallback not configured (DEEPSEEK_API_KEY empty), using Gemini only")
    return primary
