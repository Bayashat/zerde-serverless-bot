"""Provider chain for ambient emoji reaction classification."""

from __future__ import annotations

import json
import time
from typing import Protocol

import urllib3
from core.config import (
    AMBIENT_REACTIONS_DECISION_GROQ_MODELS,
    GROQ_API_BASE,
    get_groq_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.ambient_reaction_prompt import build_ambient_reaction_prompts
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
_RATE_LIMIT_COOLDOWN_SECONDS = 60 * 60
_rate_limited_until_by_model: dict[str, float] = {}


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


class OpenAICompatibleAmbientReactionProvider:
    """OpenAI-compatible chat/completions provider for ambient reactions."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=10))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self.provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        self._cooldown_key = f"{provider_name}:{model}"
        logger.info(
            "Ambient reaction provider initialized",
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
        cooldown_until = _rate_limited_until_by_model.get(self._cooldown_key, 0)
        now = time.time()
        if cooldown_until > now:
            raise ProviderRateLimitError(f"{self.provider_name} model {self._model} is cooling down after rate limit")

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
        apply_groq_chat_options(payload, model=self._model, max_output_tokens=220)

        logger.info(
            "Ambient reaction provider request started",
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
                "Ambient reaction provider API error",
                extra={
                    "provider": self.provider_name,
                    "model": self._model,
                    "status": resp.status,
                    "body": body[:500],
                },
            )
            error = map_http_status_to_provider_error(
                resp.status,
                f"{self.provider_name} API {resp.status}: {body[:200]}",
            )
            if isinstance(error, ProviderRateLimitError):
                _rate_limited_until_by_model[self._cooldown_key] = time.time() + _RATE_LIMIT_COOLDOWN_SECONDS
                logger.warning(
                    "Ambient reaction provider model entered cooldown",
                    extra={
                        "provider": self.provider_name,
                        "model": self._model,
                        "cooldown_seconds": _RATE_LIMIT_COOLDOWN_SECONDS,
                    },
                )
            raise error

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
            "Ambient reaction provider response parsed",
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
                _ensure_json_object(raw, provider_name=provider.provider_name)
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


def _ensure_json_object(raw: str, *, provider_name: str) -> None:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"{provider_name} returned invalid ambient reaction JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderResponseError(f"{provider_name} returned non-object ambient reaction JSON")


def create_ambient_reaction_classifier() -> FallbackAmbientReactionClassifier | None:
    """Build the Groq-only ambient reaction decision pool."""
    providers: list[AmbientReactionProvider] = []

    groq_api_key = get_groq_api_key()
    if groq_api_key:
        for model in AMBIENT_REACTIONS_DECISION_GROQ_MODELS:
            providers.append(
                OpenAICompatibleAmbientReactionProvider(
                    f"groq:{model}",
                    groq_api_key,
                    GROQ_API_BASE,
                    model,
                )
            )

    if not providers:
        return None
    logger.info(
        "Ambient reaction provider chain configured",
        extra={"providers": ",".join(provider.provider_name for provider in providers)},
    )
    return FallbackAmbientReactionClassifier(providers)
