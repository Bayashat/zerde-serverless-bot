"""Provider chain for ambient emoji reaction classification."""

from __future__ import annotations

import json
from typing import Protocol

import urllib3
from core.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_MODEL,
    GROQ_API_BASE,
    GROQ_MODEL,
    get_deepseek_api_key,
    get_gemini_api_key,
    get_groq_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.ambient_reaction_prompt import build_ambient_reaction_prompts
from services.ai.gemini_client import (
    GeminiClient,
    GeminiEmptyResponseError,
    GeminiRPDExhaustedError,
    GeminiUnavailableError,
)
from urllib3.exceptions import HTTPError
from zerde_common.ai_errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)

logger = LoggerAdapter(get_logger(__name__), {})


class AmbientReactionProvider(Protocol):
    provider_name: str

    def ambient_reaction_decision(
        self,
        *,
        current_message: str,
        previous_context: str = "",
        reply_context: str = "",
        allowed_emojis: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀"),
        lang: str = "kk",
    ) -> str:
        """Return raw strict-JSON classifier text or raise a provider error."""


class GeminiAmbientReactionProvider:
    """Gemini ambient reaction provider adapter."""

    provider_name = "gemini"

    def __init__(self) -> None:
        self._client = GeminiClient()

    def ambient_reaction_decision(
        self,
        *,
        current_message: str,
        previous_context: str = "",
        reply_context: str = "",
        allowed_emojis: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀"),
        lang: str = "kk",
    ) -> str:
        try:
            raw, _ = self._client.ambient_reaction_decision(
                current_message=current_message,
                previous_context=previous_context,
                reply_context=reply_context,
                allowed_emojis=allowed_emojis,
                lang=lang,
            )
            return raw
        except GeminiRPDExhaustedError as exc:
            raise ProviderRateLimitError(str(exc)) from exc
        except GeminiEmptyResponseError as exc:
            raise ProviderResponseError(str(exc)) from exc
        except GeminiUnavailableError as exc:
            raise ProviderTransportError(str(exc)) from exc


class OpenAICompatibleAmbientReactionProvider:
    """OpenAI-compatible chat/completions provider for ambient reactions."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=10))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self.provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info(
            "Ambient reaction fallback provider initialized",
            extra={"provider": provider_name, "model": model},
        )

    def ambient_reaction_decision(
        self,
        *,
        current_message: str,
        previous_context: str = "",
        reply_context: str = "",
        allowed_emojis: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀"),
        lang: str = "kk",
    ) -> str:
        system_prompt, user_prompt = build_ambient_reaction_prompts(
            current_message=current_message,
            previous_context=previous_context,
            reply_context=reply_context,
            allowed_emojis=allowed_emojis,
            lang=lang,
        )
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 220,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "Ambient reaction fallback provider request started",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "previous_context_chars": len(previous_context),
                "reply_context_chars": len(reply_context),
                "current_message_chars": len(current_message),
            },
        )
        try:
            resp = self._http.request(
                "POST",
                f"{self._api_base}/chat/completions",
                body=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                retries=False,
            )
        except (HTTPError, OSError) as exc:
            raise ProviderTransportError(f"{self.provider_name} transport error: {exc}") from exc

        if resp.status >= 400:
            body = resp.data.decode("utf-8", errors="replace")
            logger.warning(
                "Ambient reaction fallback provider API error",
                extra={"provider": self.provider_name, "status": resp.status, "body": body[:500]},
            )
            raise map_http_status_to_provider_error(
                resp.status,
                f"{self.provider_name} API {resp.status}: {body[:200]}",
            )

        try:
            data = json.loads(resp.data.decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"{self.provider_name} response was not valid JSON: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(f"{self.provider_name} response schema invalid: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError(f"{self.provider_name} returned empty ambient reaction content")
        logger.info(
            "Ambient reaction fallback provider response parsed",
            extra={"provider": self.provider_name, "model": self._model, "response_chars": len(content)},
        )
        return content.strip()


class FallbackAmbientReactionClassifier:
    """Try ambient reaction providers in order until one returns raw JSON text."""

    def __init__(self, providers: list[AmbientReactionProvider]) -> None:
        self._providers = providers

    def ambient_reaction_decision(
        self,
        *,
        current_message: str,
        previous_context: str = "",
        reply_context: str = "",
        allowed_emojis: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀"),
        lang: str = "kk",
    ) -> tuple[str, str]:
        last_error: ZerdeProviderError | None = None
        for provider in self._providers:
            try:
                raw = provider.ambient_reaction_decision(
                    current_message=current_message,
                    previous_context=previous_context,
                    reply_context=reply_context,
                    allowed_emojis=allowed_emojis,
                    lang=lang,
                )
                logger.info("Ambient reaction classified by provider", extra={"provider": provider.provider_name})
                return raw, provider.provider_name
            except ZerdeProviderError as exc:
                last_error = exc
                logger.warning(
                    "Ambient reaction provider failed, trying next provider",
                    extra={"provider": provider.provider_name, "error_type": exc.__class__.__name__},
                )
        if last_error:
            raise last_error
        raise ProviderResponseError("No ambient reaction providers configured")


def create_ambient_reaction_classifier() -> FallbackAmbientReactionClassifier | None:
    """Build Gemini -> DeepSeek -> Groq provider chain from configured keys."""
    providers: list[AmbientReactionProvider] = []
    if get_gemini_api_key():
        providers.append(GeminiAmbientReactionProvider())

    deepseek_api_key = get_deepseek_api_key()
    if deepseek_api_key and DEEPSEEK_MODEL:
        providers.append(
            OpenAICompatibleAmbientReactionProvider(
                "deepseek",
                deepseek_api_key,
                DEEPSEEK_API_BASE,
                DEEPSEEK_MODEL,
            )
        )

    groq_api_key = get_groq_api_key()
    if groq_api_key and GROQ_MODEL:
        providers.append(
            OpenAICompatibleAmbientReactionProvider(
                "groq",
                groq_api_key,
                GROQ_API_BASE,
                GROQ_MODEL,
            )
        )

    if not providers:
        return None
    logger.info(
        "Ambient reaction provider chain configured",
        extra={"providers": ",".join(provider.provider_name for provider in providers)},
    )
    return FallbackAmbientReactionClassifier(providers)
