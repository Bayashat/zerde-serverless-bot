"""Provider chain for linked-channel post comment generation."""

from __future__ import annotations

import json
from typing import Any, Protocol

import urllib3
from core.config import (
    DEEPSEEK_API_BASE,
    DEEPSEEK_MODEL,
    GROQ_API_BASE,
    GROQ_MODEL,
    get_deepseek_api_key,
    get_groq_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.gemini_client import GroupAgentDecision
from urllib3.exceptions import HTTPError
from zerde_common.ai_errors import (
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)

logger = LoggerAdapter(get_logger(__name__), {})


class ChannelPostCommentProvider(Protocol):
    provider_name: str

    def comment_decision(
        self,
        *,
        channel_post: str,
        recent_context: str = "",
        lang: str = "kk",
        reply_instructions: str = "",
        max_output_tokens: int = 220,
    ) -> GroupAgentDecision:
        """Return a linked-channel post comment decision or raise a provider error."""


def _build_channel_post_comment_prompts(
    *,
    channel_post: str,
    recent_context: str,
    lang: str,
    reply_instructions: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are the social timing layer for ZerdeBot, a Telegram group chat member in an IT community. "
        "This is an official linked-channel post mirrored into the group discussion. "
        "Write one natural follow-up comment from ZerdeBot under the post. Do not decide to stay silent. "
        "The goal is to continue the conversation under the post, not to answer a direct question and not "
        "to summarize the whole post. Pick one specific angle from the text: technical, historical, "
        "practical, product, personal productivity, finance, learning, or a surprising detail. "
        "You are a text-only fallback provider and did not receive attached media bytes. Use only the post "
        "text, caption, sender metadata, and recent text context. Do not claim visual/audio/file details. "
        "Do not praise the channel owner, do not say generic thanks, and do not sound promotional. "
        "The comment may be short or a few concise sentences depending on the post, but it must feel like a "
        "real group participant replying under the post. Prefer the group's language. "
        "Return only compact JSON with keys: should_reply (boolean), confidence (0..1), reason (short string), "
        "reply_text (string). Set should_reply=true."
    )
    user_prompt = (
        f"Preferred language code: {lang}\n\n"
        "Recent group context, oldest to newest:\n"
        f"{recent_context or '(no recent context available)'}\n\n"
        "Current official linked-channel post:\n"
        f"{channel_post}\n\n"
        "Reply style instructions:\n"
        f"{reply_instructions or 'Write a natural comment under this post.'}\n\n"
        "Write the JSON comment now."
    )
    return system_prompt, user_prompt


def _parse_decision(raw_content: str, *, provider_name: str) -> GroupAgentDecision:
    try:
        data = json.loads(raw_content)
        if not isinstance(data, dict):
            raise TypeError("provider content JSON was not an object")
        decision = GroupAgentDecision(
            should_reply=bool(data.get("should_reply", True)),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0)))),
            reason=str(data.get("reason") or "")[:200],
            reply_text=str(data.get("reply_text") or "").strip(),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProviderResponseError(f"{provider_name} returned invalid channel-post JSON: {exc}") from exc
    if not decision.should_reply or not decision.reply_text:
        raise ProviderResponseError(f"{provider_name} returned no usable channel-post comment")
    return decision


class OpenAICompatibleChannelPostCommentProvider:
    """OpenAI-compatible chat/completions provider for text-only channel-post comments."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=12))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self.provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info(
            "Channel post fallback provider initialized",
            extra={"provider": provider_name, "model": model},
        )

    def comment_decision(
        self,
        *,
        channel_post: str,
        recent_context: str = "",
        lang: str = "kk",
        reply_instructions: str = "",
        max_output_tokens: int = 220,
    ) -> GroupAgentDecision:
        system_prompt, user_prompt = _build_channel_post_comment_prompts(
            channel_post=channel_post,
            recent_context=recent_context,
            lang=lang,
            reply_instructions=reply_instructions,
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.25,
            "max_tokens": max(80, min(420, int(max_output_tokens))),
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "Channel post fallback provider request started",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "context_chars": len(recent_context),
                "message_chars": len(channel_post),
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
                "Channel post fallback provider API error",
                extra={
                    "provider": self.provider_name,
                    "status": resp.status,
                    "body": body[:500],
                },
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
            raise ProviderResponseError(f"{self.provider_name} returned empty channel-post content")
        decision = _parse_decision(content.strip(), provider_name=self.provider_name)
        logger.info(
            "Channel post fallback provider response parsed",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "response_chars": len(content),
                "confidence": decision.confidence,
            },
        )
        return decision


class FallbackChannelPostCommentProvider:
    """Try text-only channel-post comment providers in order."""

    def __init__(self, providers: list[ChannelPostCommentProvider]) -> None:
        self._providers = providers

    def comment_decision(
        self,
        *,
        channel_post: str,
        recent_context: str = "",
        lang: str = "kk",
        reply_instructions: str = "",
        max_output_tokens: int = 220,
    ) -> tuple[GroupAgentDecision, str]:
        last_error: ZerdeProviderError | None = None
        for provider in self._providers:
            try:
                decision = provider.comment_decision(
                    channel_post=channel_post,
                    recent_context=recent_context,
                    lang=lang,
                    reply_instructions=reply_instructions,
                    max_output_tokens=max_output_tokens,
                )
                logger.info(
                    "Channel post comment generated by fallback provider",
                    extra={"provider": provider.provider_name},
                )
                return decision, provider.provider_name
            except ZerdeProviderError as exc:
                last_error = exc
                logger.warning(
                    "Channel post fallback provider failed, trying next provider",
                    extra={
                        "provider": provider.provider_name,
                        "error_type": exc.__class__.__name__,
                    },
                )
        if last_error:
            raise last_error
        raise ProviderResponseError("No channel-post fallback providers configured")


def create_channel_post_comment_fallback_provider() -> FallbackChannelPostCommentProvider | None:
    """Build DeepSeek -> Groq text-only fallback chain from configured keys."""
    providers: list[ChannelPostCommentProvider] = []

    deepseek_api_key = get_deepseek_api_key()
    if deepseek_api_key and DEEPSEEK_MODEL:
        providers.append(
            OpenAICompatibleChannelPostCommentProvider(
                "deepseek",
                deepseek_api_key,
                DEEPSEEK_API_BASE,
                DEEPSEEK_MODEL,
            )
        )

    groq_api_key = get_groq_api_key()
    if groq_api_key and GROQ_MODEL:
        providers.append(
            OpenAICompatibleChannelPostCommentProvider(
                "groq",
                groq_api_key,
                GROQ_API_BASE,
                GROQ_MODEL,
            )
        )

    if not providers:
        return None
    logger.info(
        "Channel post fallback provider chain configured",
        extra={"providers": ",".join(provider.provider_name for provider in providers)},
    )
    return FallbackChannelPostCommentProvider(providers)
