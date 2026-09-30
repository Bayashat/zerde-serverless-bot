"""LLM provider abstraction with Gemini primary and DeepSeek fallback."""

import json
import random
import time
from abc import ABC, abstractmethod
from typing import Any, TypedDict

import urllib3
from core.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_MODEL,
    GEMINI_MODEL,
    GROQ_API_BASE,
    GROQ_MODEL,
    get_deepseek_api_key,
    get_gemini_api_key,
    get_groq_api_key,
)
from core.logger import LoggerAdapter, get_logger
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from services.provider_observation import ProviderAttempt
from services.rate_limit_repository import QuizQuotaUnavailable, QuizRateLimitRepository
from urllib3.exceptions import HTTPError
from zerde_common.ai_errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.groq_chat import apply_groq_chat_options

logger = LoggerAdapter(get_logger(__name__), {})


class _QuizQuestionResponse(TypedDict):
    question: str
    options: list[str]
    correct_option_index: int
    explanation: str


def _map_gemini_api_error(exc: genai_errors.APIError) -> ZerdeProviderError:
    if exc.code == 429:
        return ProviderRateLimitError("Gemini API request failed")
    if exc.code in (500, 503, 504):
        return ProviderTransportError("Gemini API request failed")
    if exc.code and 400 <= int(exc.code) < 500:
        return ProviderResponseError("Gemini API request failed")
    return ProviderResponseError("Gemini API request failed")


class RateLimitError(ProviderRateLimitError):
    """Back-compat: local RPD limit or upstream 429."""


class QuizLLMProvider(ABC):
    """Abstract interface for quiz JSON generation."""

    @abstractmethod
    def generate_json(self, prompt: str, temperature: float = 0.3, *, interactive: bool = False) -> dict:
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

    def get_rpd_status(self) -> tuple[int | None, int]:
        total = self._rate_repo.rpd_limit
        try:
            used = self._rate_repo.get_today_count()
        except QuizQuotaUnavailable:
            return None, total
        remaining = max(0, total - used)
        return remaining, total

    _SCHEDULED_RETRY_DELAYS = (5, 15, 30)  # seconds; scheduled quiz runs have time
    _INTERACTIVE_RETRY_DELAYS = (1,)  # /genquiz should fall back fast
    _SCHEDULED_TIMEOUT_MS = 60000
    _INTERACTIVE_TIMEOUT_MS = 12000

    def generate_json(self, prompt: str, temperature: float = 0.3, *, interactive: bool = False) -> dict:
        retry_delays = self._INTERACTIVE_RETRY_DELAYS if interactive else self._SCHEDULED_RETRY_DELAYS
        timeout_ms = self._INTERACTIVE_TIMEOUT_MS if interactive else self._SCHEDULED_TIMEOUT_MS
        for attempt in range(len(retry_delays) + 1):
            # Local dependency failures deliberately bypass provider fallback.
            count, within_limit = self._rate_repo.increment_and_check()
            if not within_limit:
                raise RateLimitError(f"Quiz Gemini RPD limit reached: {count}/{self._rate_repo.rpd_limit}")
            config = types.GenerateContentConfig(
                http_options=types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)),
                temperature=temperature,
                response_mime_type="application/json",
                response_schema=_QuizQuestionResponse,
                max_output_tokens=2000,
                thinking_config=_thinking_config_for_model(self._model),
            )
            observation = ProviderAttempt("Gemini", self._model)
            response = None
            try:
                response = self._client.models.generate_content(model=self._model, contents=prompt, config=config)
                text = response.text.strip()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    raise ProviderResponseError("Gemini returned invalid JSON") from None
            except genai_errors.APIError as exc:
                observation.finish("http_error", status=exc.code)
                retryable = exc.code in (500, 503, 504)
                if not retryable or attempt == len(retry_delays):
                    raise _map_gemini_api_error(exc) from None
                wait = retry_delays[attempt] + random.uniform(0, 1 if interactive else 3)
                time.sleep(wait)
            except ZerdeProviderError:
                observation.finish("response_invalid", response=response, gemini=True)
                raise
            except Exception:
                observation.finish(
                    "transport_unknown" if response is None else "response_invalid", response=response, gemini=True
                )
                raise
            else:
                observation.finish("success", response=response, gemini=True)
                return data


def _thinking_config_for_model(model: str | None) -> types.ThinkingConfig | None:
    """Keep lightweight quiz generation low-latency on thinking-capable models."""
    if not model:
        return None
    if model.startswith("gemini-3."):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    if model.startswith("gemini-2.5"):
        return types.ThinkingConfig(thinking_budget=0)
    return None


class OpenAICompatibleQuizProvider(QuizLLMProvider):
    """OpenAI-compatible chat/completions provider."""

    _scheduled_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=5, read=60))
    _interactive_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=12))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self._provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info("OpenAI-compatible Quiz provider initialized", extra={"provider": provider_name, "model": model})

    def generate_json(self, prompt: str, temperature: float = 0.3, *, interactive: bool = False) -> dict:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if self._provider_name == "Groq":
            apply_groq_chat_options(payload, model=self._model, max_output_tokens=1024)

        observation = ProviderAttempt(self._provider_name, self._model)
        try:
            http = self._interactive_http if interactive else self._scheduled_http
            resp = http.request(
                "POST",
                f"{self._api_base}/chat/completions",
                body=json.dumps(payload),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
                retries=False,
            )
        except (HTTPError, OSError):
            observation.finish("transport_unknown")
            raise ProviderTransportError("Quiz provider transport unavailable") from None
        except Exception:
            observation.finish("transport_unknown")
            raise
        if resp.status >= 400:
            observation.finish("http_error", status=resp.status, response={})
            raise map_http_status_to_provider_error(resp.status, "Quiz provider API request failed") from None
        data = None
        try:
            try:
                data = json.loads(resp.data.decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                raise ProviderResponseError("Quiz provider returned invalid JSON or schema") from None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                raise ProviderResponseError("Quiz provider returned invalid content JSON") from None
        except Exception:
            observation.finish("response_invalid", status=resp.status, response=data if data is not None else {})
            raise
        observation.finish("success", status=resp.status, response=data)
        return result


class DeepSeekQuizProvider(OpenAICompatibleQuizProvider):
    """DeepSeek provider via OpenAI-compatible chat/completions endpoint."""

    def __init__(self, api_key: str, api_base: str, model: str) -> None:
        super().__init__("DeepSeek", api_key, api_base, model)


class GroqQuizProvider(OpenAICompatibleQuizProvider):
    """Groq provider via OpenAI-compatible chat/completions endpoint."""

    def __init__(self, api_key: str, api_base: str, model: str) -> None:
        super().__init__("Groq", api_key, api_base, model)


class FallbackProvider(QuizLLMProvider):
    """Tries providers in order, falling through on mapped provider errors."""

    def __init__(self, providers: list[QuizLLMProvider]) -> None:
        self._providers = providers

    def generate_json(self, prompt: str, temperature: float = 0.3, *, interactive: bool = False) -> dict:
        last_error: ZerdeProviderError | None = None
        for index, provider in enumerate(self._providers):
            try:
                return provider.generate_json(prompt, temperature, interactive=interactive)
            except ZerdeProviderError as e:
                last_error = e
                try:
                    logger.warning(
                        "Quiz provider failed, trying next provider",
                        extra={"provider_index": index, "error_type": type(e).__name__},
                    )
                except Exception:
                    pass  # A diagnostic must not alter the established fallback policy.
        if last_error:
            raise last_error
        raise ProviderResponseError("No quiz providers configured")

    def get_rpd_status(self) -> tuple[int | None, int | None]:
        return self._providers[0].get_rpd_status() if self._providers else (None, None)


def create_provider() -> QuizLLMProvider:
    """Build the provider chain: Gemini primary -> DeepSeek -> Groq when configured."""
    providers: list[QuizLLMProvider] = [GeminiQuizProvider(api_key=get_gemini_api_key(), model=GEMINI_MODEL)]

    deepseek_api_key = get_deepseek_api_key()
    if deepseek_api_key:
        providers.append(
            DeepSeekQuizProvider(api_key=deepseek_api_key, api_base=DEEPSEEK_API_BASE, model=DEEPSEEK_MODEL)
        )

    groq_api_key = get_groq_api_key()
    if groq_api_key and GROQ_MODEL:
        providers.append(GroqQuizProvider(api_key=groq_api_key, api_base=GROQ_API_BASE, model=GROQ_MODEL))

    if len(providers) > 1:
        logger.info(
            "Quiz fallback provider chain configured",
            extra={"provider_count": len(providers), "primary": GEMINI_MODEL},
        )
        return FallbackProvider(providers)

    logger.info("Quiz fallback providers not configured, using Gemini only")
    return providers[0]
