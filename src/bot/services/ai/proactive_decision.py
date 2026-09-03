"""Provider chain for ordinary proactive answer decisions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import urllib3
from core.config import (
    AGENT_PROACTIVE_DECISION_ALLOW_DEEPSEEK_FALLBACK,
    AGENT_PROACTIVE_DECISION_GROQ_MODELS,
    DEEPSEEK_API_BASE,
    DEEPSEEK_MODEL,
    GROQ_API_BASE,
    get_deepseek_api_key,
    get_groq_api_key,
)
from core.logger import LoggerAdapter, get_logger
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


@dataclass(frozen=True)
class ProactiveDecision:
    should_reply: bool
    confidence: float
    reason: str
    answer_guidance: str = ""


class ProactiveDecisionProvider(Protocol):
    provider_name: str

    def decide(
        self,
        *,
        current_message: str,
        recent_context: str = "",
        long_term_memory_context: str = "",
        reply_instructions: str = "",
        lang: str = "kk",
    ) -> ProactiveDecision:
        """Return a strict proactive decision or raise a provider error."""


def _language_instruction(lang: str) -> str:
    return (
        f"If a later answer is generated, it must use configured chat language code {lang}, even when the "
        "current user's message uses another language. The only exception is an explicit request to translate "
        "or answer in a different language."
    )


def _build_prompts(
    *,
    current_message: str,
    recent_context: str,
    long_term_memory_context: str,
    reply_instructions: str,
    lang: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are ZerdeBot's proactive participation decision layer for a Telegram IT community. "
        "You only decide whether ZerdeBot should answer an ordinary group message that was not necessarily "
        "addressed to the bot. The default decision is should_reply=false. "
        "Before deciding, infer the social permission to speak: who the current message is for, what kind of "
        "speech act it is, whether a bot has concrete incremental value, and whether the recent context makes "
        "a bot interjection welcome or noisy. Be conservative, but do not require fixed local patterns like "
        "question marks: users may write messy, multilingual, informal, implicit requests. "
        "Say should_reply=true only when all of these are clearly true: "
        "the message is addressed to the whole group or reasonably invites anyone to help; "
        "the message contains an explicit or strong implicit request for technical/practical help, explanation, "
        "debugging, advice, study/career/product reasoning, or useful context; "
        "ZerdeBot can add something specific beyond a generic acknowledgement; "
        "and humans have not already answered sufficiently in the recent context. "
        "Choose should_reply=false for ordinary chatter, pure jokes/laughter, rhetorical remarks, FYI/status "
        "updates, announcements, reactions, praise, congratulations, private interpersonal moments, "
        "human-directed messages, bot-meta complaints, stop cues, or ambiguous messages. "
        "If the message is mainly addressed to one specific person or a small side conversation, choose "
        "should_reply=false unless it also clearly asks the group for help. If it merely mentions AI, bots, "
        "Codex, language support, a tool name, or a topic ZerdeBot knows about, that is not enough. "
        "If you are unsure about audience, intent, or incremental value, choose should_reply=false. "
        "Sensitive, hostile, sad, medical, legal, financial, political, religious, or conflict-heavy messages "
        "are allowed as input, but choose silence unless a short, safe, non-escalating answer would genuinely "
        "help. Never encourage harm, mock people, or intensify conflict. "
        f"{_language_instruction(lang)} "
        "Return only compact JSON with keys: should_reply (boolean), confidence (0..1), reason (short string), "
        "answer_guidance (short string; empty when silent). The reason should mention the audience/intent/value "
        "judgment. Do not include the final answer text."
    )
    user_prompt = (
        f"{_language_instruction(lang)}\n\n"
        "Trusted long-term group memory, query-filtered for this message:\n"
        f"{long_term_memory_context or '(no long-term memory available)'}\n\n"
        "Recent group context, oldest to newest:\n"
        f"{recent_context or '(no recent context available)'}\n\n"
        "Proactive reply style constraints if you choose should_reply=true:\n"
        f"{reply_instructions or 'The eventual reply should be concise, natural, and useful.'}\n\n"
        "Decision checklist:\n"
        "1. Intended audience: whole group / bot / specific human / side conversation / unclear.\n"
        "2. Conversation act: help request / advice request / debugging / discussion invitation / FYI / "
        "status update / reaction / chatter / other.\n"
        "3. Incremental value: what specific useful thing could ZerdeBot add beyond a generic acknowledgement?\n"
        "4. Timing: have humans already answered or is the exchange better left to people?\n"
        "Return should_reply=true only when social permission and incremental value are both clearly present.\n\n"
        "Current ordinary group message:\n"
        f"{current_message}\n\n"
        "Should ZerdeBot proactively answer this message?"
    )
    return system_prompt, user_prompt


def _parse_decision(raw_content: str, *, provider_name: str) -> ProactiveDecision:
    try:
        raw = json.loads(raw_content)
        if not isinstance(raw, dict):
            raise TypeError("decision JSON was not an object")
        if "should_reply" not in raw or "confidence" not in raw or "reason" not in raw:
            raise KeyError("missing required decision field")
        should_reply = raw["should_reply"]
        if not isinstance(should_reply, bool):
            raise TypeError("should_reply must be boolean")
        confidence = max(0.0, min(1.0, float(raw["confidence"])))
        reason = str(raw["reason"] or "")[:300]
        answer_guidance = str(raw.get("answer_guidance") or "").strip()[:600]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ProviderResponseError(f"{provider_name} returned invalid proactive decision JSON: {exc}") from exc
    return ProactiveDecision(
        should_reply=should_reply,
        confidence=confidence,
        reason=reason,
        answer_guidance=answer_guidance if should_reply else "",
    )


class OpenAICompatibleProactiveDecisionProvider:
    """OpenAI-compatible chat/completions provider for proactive decisions."""

    _http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=10))

    def __init__(self, provider_name: str, api_key: str, api_base: str, model: str) -> None:
        self.provider_name = provider_name
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._model = model
        self._cooldown_key = f"{provider_name}:{model}"
        logger.info(
            "Proactive decision provider initialized",
            extra={"provider": provider_name, "model": model},
        )

    def decide(
        self,
        *,
        current_message: str,
        recent_context: str = "",
        long_term_memory_context: str = "",
        reply_instructions: str = "",
        lang: str = "kk",
    ) -> ProactiveDecision:
        cooldown_until = _rate_limited_until_by_model.get(self._cooldown_key, 0)
        now = time.time()
        if cooldown_until > now:
            raise ProviderRateLimitError(f"{self.provider_name} model {self._model} is cooling down after rate limit")

        system_prompt, user_prompt = _build_prompts(
            current_message=current_message,
            recent_context=recent_context,
            long_term_memory_context=long_term_memory_context,
            reply_instructions=reply_instructions,
            lang=lang,
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 260,
            "response_format": {"type": "json_object"},
        }
        if self.provider_name.startswith("groq:"):
            apply_groq_chat_options(payload, model=self._model, max_output_tokens=260)

        logger.info(
            "Proactive decision provider request started",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "context_chars": len(recent_context),
                "long_term_memory_chars": len(long_term_memory_context),
                "message_chars": len(current_message),
                "lang": lang,
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
                "Proactive decision provider API error",
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
                    "Proactive decision provider model entered cooldown",
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
            raise ProviderResponseError(f"{self.provider_name} returned empty proactive decision content")
        decision = _parse_decision(content.strip(), provider_name=self.provider_name)
        logger.info(
            "Proactive decision provider response parsed",
            extra={
                "provider": self.provider_name,
                "model": self._model,
                "should_reply": decision.should_reply,
                "confidence": decision.confidence,
            },
        )
        return decision


class FallbackProactiveDecisionProvider:
    """Try proactive decision providers in order until one returns valid JSON."""

    def __init__(self, providers: list[ProactiveDecisionProvider]) -> None:
        self._providers = providers

    def decide(
        self,
        *,
        current_message: str,
        recent_context: str = "",
        long_term_memory_context: str = "",
        reply_instructions: str = "",
        lang: str = "kk",
    ) -> tuple[ProactiveDecision, str]:
        last_error: ZerdeProviderError | None = None
        for provider in self._providers:
            try:
                decision = provider.decide(
                    current_message=current_message,
                    recent_context=recent_context,
                    long_term_memory_context=long_term_memory_context,
                    reply_instructions=reply_instructions,
                    lang=lang,
                )
                logger.info("Proactive decision made by provider", extra={"provider": provider.provider_name})
                return decision, provider.provider_name
            except ZerdeProviderError as exc:
                last_error = exc
                logger.warning(
                    "Proactive decision provider failed, trying next provider",
                    extra={"provider": provider.provider_name, "error_type": exc.__class__.__name__},
                )
        if last_error:
            raise last_error
        raise ProviderResponseError("No proactive decision providers configured")


def create_proactive_decision_provider() -> FallbackProactiveDecisionProvider | None:
    """Build the Groq-only proactive decision pool, with optional DeepSeek fallback."""
    providers: list[ProactiveDecisionProvider] = []

    groq_api_key = get_groq_api_key()
    if groq_api_key:
        for model in AGENT_PROACTIVE_DECISION_GROQ_MODELS:
            providers.append(
                OpenAICompatibleProactiveDecisionProvider(
                    f"groq:{model}",
                    groq_api_key,
                    GROQ_API_BASE,
                    model,
                )
            )

    if AGENT_PROACTIVE_DECISION_ALLOW_DEEPSEEK_FALLBACK:
        deepseek_api_key = get_deepseek_api_key()
        if deepseek_api_key and DEEPSEEK_MODEL:
            providers.append(
                OpenAICompatibleProactiveDecisionProvider(
                    "deepseek",
                    deepseek_api_key,
                    DEEPSEEK_API_BASE,
                    DEEPSEEK_MODEL,
                )
            )

    if not providers:
        return None
    logger.info(
        "Proactive decision provider chain configured",
        extra={"providers": ",".join(provider.provider_name for provider in providers)},
    )
    return FallbackProactiveDecisionProvider(providers)
