"""Provider chain for text-only group-agent replies."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

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
from services.explicit_context import (
    CONTEXT_EVIDENCE_INSTRUCTIONS,
    EXPLICIT_ANSWER_POLICY,
    PUBLIC_SOURCE_INSTRUCTIONS,
    format_explicit_context_sections,
)
from urllib3.exceptions import HTTPError
from zerde_common.ai_errors import (
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.groq_chat import apply_groq_chat_options

logger = LoggerAdapter(get_logger(__name__), {})


class GroupChatReplyProvider(Protocol):
    provider_name: str

    def generate_reply(
        self,
        *,
        user_message: str,
        recent_context: str,
        long_term_memory_context: str = "",
        semantic_memory_context: str = "",
        user_profile_context: str = "",
        requester_profile_context: str = "",
        reply_instructions: str = "",
        max_output_tokens: int = 320,
        lang: str = "kk",
        text_only_media_context: str = "",
        public_source_context: str = "",
        before_attempt: Callable[[], None] | None = None,
    ) -> str:
        """Return plain answer text or raise a provider error."""


def _language_instruction(lang: str) -> str:
    return (
        f"Mandatory response language code: {lang}. "
        "Write the final Telegram reply in that configured chat language even if the current user message "
        "uses another language. Switch language only when the user explicitly asks for translation or asks "
        "you to answer in a different language."
    )


def _build_group_chat_reply_prompts(
    *,
    user_message: str,
    recent_context: str,
    long_term_memory_context: str,
    semantic_memory_context: str,
    user_profile_context: str,
    requester_profile_context: str,
    reply_instructions: str,
    lang: str,
    text_only_media_context: str,
    public_source_context: str = "",
) -> tuple[str, str]:
    media_instructions = (
        "The user attached media, but this fallback provider receives text only. "
        "Use any supplied text media content, captions, filenames, or metadata, but do not claim to see images, "
        "hear audio, inspect PDFs, or read binary files unless the text content is explicitly included below. "
        "If media details are necessary and unavailable, say that briefly and answer what can be answered from text. "
        if text_only_media_context
        else ""
    )
    context_prompt_section = format_explicit_context_sections(
        requester_profile_context=requester_profile_context,
        user_profile_context=user_profile_context,
        semantic_memory_context=semantic_memory_context,
        long_term_memory_context=long_term_memory_context,
        recent_context=recent_context,
    )
    system_prompt = (
        f"{_language_instruction(lang)} "
        f"{EXPLICIT_ANSWER_POLICY}"
        f"{PUBLIC_SOURCE_INSTRUCTIONS if public_source_context else ''}"
        f"{CONTEXT_EVIDENCE_INSTRUCTIONS if context_prompt_section else ''}"
        f"{media_instructions}"
        "Decide the answer style from the user's wording and the replied-to context. "
        "Answer naturally and directly. "
        "Respect the response length instructions exactly; short follow-ups should stay short. "
        "Keep replies concise and natural. "
        "Avoid mentioning that you are using stored memory unless asked. "
        "Return only the message text to send to Telegram, not JSON."
    )
    media_prompt_section = (
        "Text-only attached media context:\n" f"{text_only_media_context}\n\n" if text_only_media_context else ""
    )
    current_label = "Current message directed at you:"
    user_prompt = (
        f"{_language_instruction(lang)}\n\n"
        f"{context_prompt_section}"
        f"{media_prompt_section}"
        "Response length and style instructions:\n"
        f"{reply_instructions or 'Answer in 2-5 concise sentences unless the user asks for more detail.'}\n\n"
        f"{current_label}\n"
        f"{user_message}\n\n"
        "Reply to the current message."
        f"{public_source_context}"
    )
    return system_prompt, user_prompt


class OpenAICompatibleGroupChatReplyProvider:
    """OpenAI-compatible chat/completions provider for text-only group replies."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=12))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self.provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        logger.info(
            "Group chat reply fallback provider initialized",
            extra={"provider": provider_name, "model": model},
        )

    def generate_reply(
        self,
        *,
        user_message: str,
        recent_context: str,
        long_term_memory_context: str = "",
        semantic_memory_context: str = "",
        user_profile_context: str = "",
        requester_profile_context: str = "",
        reply_instructions: str = "",
        max_output_tokens: int = 320,
        lang: str = "kk",
        text_only_media_context: str = "",
        public_source_context: str = "",
        before_attempt: Callable[[], None] | None = None,
    ) -> str:
        system_prompt, user_prompt = _build_group_chat_reply_prompts(
            user_message=user_message,
            recent_context=recent_context,
            long_term_memory_context=long_term_memory_context,
            semantic_memory_context=semantic_memory_context,
            user_profile_context=user_profile_context,
            requester_profile_context=requester_profile_context,
            reply_instructions=reply_instructions,
            lang=lang,
            text_only_media_context=text_only_media_context,
            **({"public_source_context": public_source_context} if public_source_context else {}),
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.55,
            "max_tokens": max(80, min(700, int(max_output_tokens))),
        }
        if self.provider_name == "groq":
            apply_groq_chat_options(
                payload,
                model=self._model,
                max_output_tokens=max(80, min(700, int(max_output_tokens))),
            )

        logger.info(
            "Group chat reply fallback provider request started",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "context_chars": len(recent_context),
                "long_term_memory_chars": len(long_term_memory_context),
                "semantic_memory_chars": len(semantic_memory_context),
                "profile_context_chars": len(user_profile_context),
                "requester_profile_context_chars": len(requester_profile_context),
                "media_context_chars": len(text_only_media_context),
                "message_chars": len(user_message),
                "lang": lang,
            },
        )
        if before_attempt is not None:
            before_attempt()  # Failures here are control/DB failures, never provider failover.
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
            raise ProviderTransportError(f"{self.provider_name} transport {type(exc).__name__}") from None

        if resp.status != 200:
            logger.warning(
                "Group chat reply fallback provider API error",
                extra={
                    "provider": self.provider_name,
                    "status": resp.status,
                },
            )
            raise map_http_status_to_provider_error(
                resp.status,
                f"{self.provider_name} API status {resp.status}",
            )

        try:
            data = json.loads(resp.data.decode("utf-8"))
            choices = data.get("choices") if isinstance(data, dict) else None
            if not isinstance(choices, list) or len(choices) != 1:
                raise ProviderResponseError("Expected one complete response choice")
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
                raise ProviderResponseError("Provider response did not finish normally")
            message = choice.get("message")
            if (
                not isinstance(message, dict)
                or message.get("role") != "assistant"
                or message.get("tool_calls") not in (None, [])
                or message.get("function_call") is not None
                or message.get("refusal") not in (None, "")
            ):
                raise ProviderResponseError("Provider response is not a final assistant message")
            content = message.get("content")
        except (UnicodeError, json.JSONDecodeError):
            raise ProviderResponseError("Provider response was not valid JSON") from None
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseError(f"{self.provider_name} returned empty group chat reply content")
        logger.info(
            "Group chat reply fallback provider response parsed",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "response_chars": len(content),
            },
        )
        return content.strip()


class FallbackGroupChatReplyProvider:
    """Try text-only group reply providers in order."""

    def __init__(self, providers: list[GroupChatReplyProvider]) -> None:
        self._providers = providers

    def generate_reply(
        self,
        *,
        user_message: str,
        recent_context: str,
        long_term_memory_context: str = "",
        semantic_memory_context: str = "",
        user_profile_context: str = "",
        requester_profile_context: str = "",
        reply_instructions: str = "",
        max_output_tokens: int = 320,
        lang: str = "kk",
        text_only_media_context: str = "",
        public_source_context: str = "",
        before_attempt: Callable[[], None] | None = None,
    ) -> tuple[str, str]:
        last_error: ZerdeProviderError | None = None
        for provider in self._providers:
            if before_attempt is not None:
                before_attempt()
            try:
                answer = provider.generate_reply(
                    user_message=user_message,
                    recent_context=recent_context,
                    long_term_memory_context=long_term_memory_context,
                    semantic_memory_context=semantic_memory_context,
                    user_profile_context=user_profile_context,
                    requester_profile_context=requester_profile_context,
                    reply_instructions=reply_instructions,
                    max_output_tokens=max_output_tokens,
                    lang=lang,
                    text_only_media_context=text_only_media_context,
                    **({"public_source_context": public_source_context} if public_source_context else {}),
                    **({"before_attempt": before_attempt} if before_attempt is not None else {}),
                )
                logger.info(
                    "Group chat reply generated by fallback provider",
                    extra={"provider": provider.provider_name},
                )
                return answer, provider.provider_name
            except ZerdeProviderError as exc:
                last_error = exc
                logger.warning(
                    "Group chat reply fallback provider failed, trying next provider",
                    extra={
                        "provider": provider.provider_name,
                        "error_type": exc.__class__.__name__,
                    },
                )
        if last_error:
            raise last_error
        raise ProviderResponseError("No group chat reply fallback providers configured")


def create_group_chat_reply_fallback_provider() -> FallbackGroupChatReplyProvider | None:
    """Build DeepSeek -> Groq text-only fallback chain from configured keys."""
    providers: list[GroupChatReplyProvider] = []

    deepseek_api_key = get_deepseek_api_key()
    if deepseek_api_key and DEEPSEEK_MODEL:
        providers.append(
            OpenAICompatibleGroupChatReplyProvider("deepseek", deepseek_api_key, DEEPSEEK_API_BASE, DEEPSEEK_MODEL)
        )

    groq_api_key = get_groq_api_key()
    if groq_api_key and GROQ_MODEL:
        providers.append(OpenAICompatibleGroupChatReplyProvider("groq", groq_api_key, GROQ_API_BASE, GROQ_MODEL))

    if not providers:
        return None
    logger.info(
        "Group chat reply fallback provider chain configured",
        extra={"providers": ",".join(provider.provider_name for provider in providers)},
    )
    return FallbackGroupChatReplyProvider(providers)
