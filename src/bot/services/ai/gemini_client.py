"""Gemini REST API client for explicit group replies.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups. The "day" matches
Gemini/Google: calendar date in America/Los_Angeles (midnight PT reset).

Group-agent commands that may call Gemini are queued through SQS so the Telegram
webhook can return quickly and avoid duplicate update retries.
"""

import json
import time
from typing import Any, Callable

import urllib3
from core.config import GEMINI_API_BASE, GEMINI_MODEL, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from services.explicit_context import (
    CONTEXT_EVIDENCE_INSTRUCTIONS,
    EXPLICIT_ANSWER_POLICY,
    PUBLIC_SOURCE_INSTRUCTIONS,
    format_explicit_context_sections,
)
from services.repositories.rate_limit import RateLimitRepository
from urllib3.exceptions import HTTPError

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=2, read=10))

_CIRCUIT_OPEN_SECONDS = 45
_CIRCUIT_FAILURE_THRESHOLD = 2
_circuit_open_until = 0.0
_circuit_failures = 0


def _thinking_config_for_model(model: str) -> dict[str, Any] | None:
    """Disable Gemini thinking for short bot responses to reduce latency variance."""
    if model.startswith("gemini-3."):
        return {"thinkingLevel": "minimal"}
    if model.startswith("gemini-2.5"):
        return {"thinkingBudget": 0}
    # Keep unset for unknown model families to avoid sending unsupported fields.
    return None


def _circuit_is_open() -> bool:
    return time.monotonic() < _circuit_open_until


def _record_transient_failure() -> None:
    global _circuit_failures, _circuit_open_until
    _circuit_failures += 1
    if _circuit_failures >= _CIRCUIT_FAILURE_THRESHOLD:
        _circuit_open_until = time.monotonic() + _CIRCUIT_OPEN_SECONDS
        logger.warning(
            "Gemini circuit opened",
            extra={
                "open_seconds": _CIRCUIT_OPEN_SECONDS,
                "failures": _circuit_failures,
            },
        )


def _record_success() -> None:
    global _circuit_failures, _circuit_open_until
    _circuit_failures = 0
    _circuit_open_until = 0.0


class GeminiRPDExhaustedError(Exception):
    """Daily RPD quota is exhausted (DynamoDB counter over limit)."""


class GeminiQuotaUnavailableError(RuntimeError):
    """Local admission is unconfirmed; do not retry or switch providers."""


class GeminiUnavailableError(Exception):
    """Transient Gemini failure: HTTP 429/5xx, timeout, network, parse errors.

    Callers should fall back to the configured OpenAI-compatible provider *without*
    the daily-quota user notice.
    """

    retryable = True


class GeminiEmptyResponseError(GeminiUnavailableError):
    """Gemini returned HTTP 200 but no usable candidate text.

    This usually means the response was blocked or otherwise completed without
    text. Retrying the same interactive SQS task is unlikely to help and can
    create noisy Lambda errors.
    """

    retryable = False


def _elapsed_ms(started_at: float) -> int:
    return int((time.monotonic() - started_at) * 1000)


def _extract_gemini_text(data: dict[str, Any], *, operation: str, model: str) -> str:
    """Accept only a complete final text response; never expose thinking/tool parts."""
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        _raise_empty_response(
            data,
            operation=operation,
            model=model,
            empty_reason="missing_or_multiple_candidates",
        )
    candidate = candidates[0]
    if not isinstance(candidate, dict) or candidate.get("finishReason") != "STOP":
        _raise_empty_response(data, operation=operation, model=model, empty_reason="incomplete_candidate")
    feedback = data.get("promptFeedback", {})
    if not isinstance(feedback, dict) or feedback.get("blockReason") not in (
        None,
        "",
        "BLOCK_REASON_UNSPECIFIED",
    ):
        _raise_empty_response(data, operation=operation, model=model, empty_reason="blocked_prompt")
    candidate_ratings = candidate.get("safetyRatings", [])
    prompt_ratings = feedback.get("safetyRatings", [])
    if not isinstance(candidate_ratings, list) or not isinstance(prompt_ratings, list):
        _raise_empty_response(data, operation=operation, model=model, empty_reason="invalid_safety_ratings")
    ratings = candidate_ratings + prompt_ratings
    if not isinstance(ratings, list) or any(
        not isinstance(rating, dict)
        or ("blocked" in rating and type(rating["blocked"]) is not bool)
        or rating.get("blocked") is True
        for rating in ratings
    ):
        _raise_empty_response(data, operation=operation, model=model, empty_reason="blocked_candidate")
    content = candidate.get("content")
    if not isinstance(content, dict) or content.get("role") != "model":
        _raise_empty_response(data, operation=operation, model=model, empty_reason="invalid_content")
    parts = content.get("parts")
    if not isinstance(parts, list) or not parts:
        _raise_empty_response(data, operation=operation, model=model, empty_reason="missing_text")
    texts = []
    for part in parts:
        if (
            not isinstance(part, dict)
            or set(part) - {"text", "thought", "thoughtSignature"}
            or not isinstance(part.get("text"), str)
            or ("thought" in part and type(part["thought"]) is not bool)
            or ("thoughtSignature" in part and not isinstance(part["thoughtSignature"], str))
        ):
            _raise_empty_response(data, operation=operation, model=model, empty_reason="unsupported_part")
        if part.get("thought") is not True:
            texts.append(part["text"])
    text = "".join(texts).strip()
    if not text:
        _raise_empty_response(data, operation=operation, model=model, empty_reason="missing_final_text")
    return text


def _raise_empty_response(
    data: dict[str, Any],
    *,
    operation: str,
    model: str,
    empty_reason: str,
) -> None:
    # Only fixed local failure codes and configured model metadata are logged.
    # Provider block messages, keys and opaque fields can contain user content.
    logger.warning(
        "Gemini response had no complete final text",
        extra={"operation": operation, "model": model, "empty_reason": empty_reason},
    )
    raise GeminiEmptyResponseError("Gemini response unusable: " + empty_reason)


class GeminiClient:
    """Thin urllib3 wrapper around the Gemini generateContent REST endpoint."""

    def __init__(self) -> None:
        api_key = get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be set to initialize GeminiClient")
        self._api_key = api_key
        self._model = GEMINI_MODEL
        self._rate_repo = RateLimitRepository()
        logger.info("GeminiClient initialized", extra={"model": self._model})

    @property
    def rpd_limit(self) -> int:
        return self._rate_repo.rpd_limit

    def _post_generate_content(
        self,
        *,
        operation: str,
        url: str,
        body: str,
        headers: dict[str, str],
        before_attempt: Callable[[], None] | None = None,
    ) -> bytes:
        if before_attempt is not None:
            before_attempt()  # Outside transport handling: a failed source fence cannot fall back.
        started_at = time.monotonic()
        try:
            resp = _http.request("POST", url, body=body, headers=headers, retries=False)
        except (HTTPError, OSError) as exc:
            _record_transient_failure()
            logger.warning(
                "Gemini request transport failed",
                extra={
                    "operation": operation,
                    "model": self._model,
                    "latency_ms": _elapsed_ms(started_at),
                    "error_type": exc.__class__.__name__,
                },
            )
            raise GeminiUnavailableError(f"Gemini transport {exc.__class__.__name__}") from None

        latency_ms = _elapsed_ms(started_at)
        response_chars = len(resp.data or b"")
        if resp.status == 429 or resp.status >= 500:
            _record_transient_failure()
            logger.warning(
                "Gemini request failed",
                extra={
                    "operation": operation,
                    "model": self._model,
                    "error_type": "http_status",
                    "status_code": resp.status,
                    "latency_ms": latency_ms,
                    "response_chars": response_chars,
                },
            )
            raise GeminiUnavailableError(f"Gemini API status {resp.status}")
        if resp.status != 200:
            logger.warning(
                "Gemini request rejected",
                extra={
                    "operation": operation,
                    "model": self._model,
                    "error_type": "http_status",
                    "status_code": resp.status,
                    "latency_ms": latency_ms,
                    "response_chars": response_chars,
                },
            )
            raise GeminiUnavailableError(f"Gemini API status {resp.status}")

        logger.info(
            "Gemini request completed",
            extra={
                "operation": operation,
                "model": self._model,
                "status_code": resp.status,
                "latency_ms": latency_ms,
                "response_chars": response_chars,
            },
        )
        return resp.data or b""

    def group_chat_reply(
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
        media_parts: list[dict[str, Any]] | None = None,
        media_context: str = "",
        public_source_context: str = "",
        before_attempt: Callable[[], None] | None = None,
    ) -> tuple[str, int]:
        """Generate a context-aware reply for an explicitly bot-directed group message."""
        if _circuit_is_open():
            logger.warning(
                "Gemini circuit open, skipping group agent request",
                extra={"model": self._model},
            )
            raise GeminiUnavailableError("Gemini circuit open")

        admission = self._rate_repo.increment_and_check()
        try:
            count, within_limit = admission
        except (TypeError, ValueError):
            raise GeminiQuotaUnavailableError("Gemini quota admission unavailable") from None
        if type(count) is not int or count < 1 or type(within_limit) is not bool:
            raise GeminiQuotaUnavailableError("Gemini quota admission unavailable")
        if not within_limit:
            logger.warning(
                "Gemini RPD limit reached (group agent)",
                extra={"count": count, "limit": self.rpd_limit},
            )
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        media_instructions = (
            "When attached media is provided, it is present only because the user explicitly asked about it. "
            "Analyze the media only for the current answer. Do not claim that media has been stored as memory. "
            "Do not infer private facts beyond what is visible, audible, or present in the attached file. "
            "If OCR, transcription, visual details, or file content are unclear, say that briefly. "
            "For screenshots, logs, and errors, focus on visible evidence and next debugging steps. "
            "For architecture diagrams, explain components, data flow, risks, and likely improvements. "
            "For voice or audio, transcribe, summarize, or explain according to the user's request. "
            "For files, summarize or explain the content according to the user's question. "
            if media_parts or media_context
            else ""
        )
        language_instructions = (
            f"Mandatory response language code: {lang}. Write the final Telegram reply in that configured "
            "chat language even if the current user message uses another language. Switch language only when "
            "the user explicitly asks for translation or asks you to answer in a different language. "
        )
        context_prompt_section = format_explicit_context_sections(
            requester_profile_context=requester_profile_context,
            user_profile_context=user_profile_context,
            semantic_memory_context=semantic_memory_context,
            long_term_memory_context=long_term_memory_context,
            recent_context=recent_context,
        )
        system_prompt = (
            f"{language_instructions}"
            f"{EXPLICIT_ANSWER_POLICY}"
            f"{PUBLIC_SOURCE_INSTRUCTIONS if public_source_context else ''}"
            f"{CONTEXT_EVIDENCE_INSTRUCTIONS if context_prompt_section else ''}"
            f"{media_instructions}"
            "Decide the answer style from the user's wording and the replied-to context: "
            "for IT terms or technical concepts, give a clear technical explanation; "
            "for questions about a replied-to group message, explain the message in context; "
            "for questions about whether someone is joking, being sarcastic, or implying something, use the "
            "recent group context and answer carefully without overclaiming; "
            "if the user explicitly asks for a harsher, cynical, or playful tone, you may match that request "
            "briefly, but do not use a fixed angry persona by default; "
            "for normal questions, stay natural, concise, and conversational like a group member. "
            "Answer naturally and directly; do not add disclaimers about not being able to characterize people. "
            "Respect the response length instructions exactly; short follow-ups should stay short. "
            "Keep replies concise, natural, and in the configured chat language. "
            "Avoid mentioning that you are using stored memory unless asked."
        )
        generation_config: dict[str, Any] = {
            "temperature": 0.75,
            "maxOutputTokens": max(80, min(700, int(max_output_tokens))),
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        media_prompt_section = (
            "Explicitly attached media metadata:\n"
            f"{media_context or '(attached media provided without extra metadata)'}\n\n"
            if media_parts or media_context
            else ""
        )
        current_label = "Current message directed at you:"
        prompt = (
            f"{language_instructions}\n\n"
            f"{context_prompt_section}"
            f"{media_prompt_section}"
            "Response length and style instructions:\n"
            f"{reply_instructions or 'Answer in 2-5 concise sentences unless the user asks for more detail.'}\n\n"
            f"{current_label}\n"
            f"{user_message}\n\n"
            "Reply to the current message."
            f"{public_source_context}"
        )
        content_parts: list[dict[str, Any]] = [{"text": prompt}]
        if media_parts:
            content_parts.extend(media_parts)
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": content_parts}],
            "generationConfig": generation_config,
        }

        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        logger.info(
            "Gemini group agent request started",
            extra={
                "model": self._model,
                "lang": lang,
                "context_chars": len(recent_context),
                "long_term_memory_chars": len(long_term_memory_context),
                "semantic_memory_chars": len(semantic_memory_context),
                "profile_context_chars": len(user_profile_context),
                "requester_profile_context_chars": len(requester_profile_context),
                "media_context_chars": len(media_context),
                "media_part_count": len(media_parts or []),
                "message_chars": len(user_message),
                "rpd_count": count,
                "rpd_limit": self.rpd_limit,
            },
        )
        resp_data = self._post_generate_content(
            operation="group_chat_reply",
            url=url,
            body=body,
            headers=headers,
            **({"before_attempt": before_attempt} if before_attempt is not None else {}),
        )

        try:
            data = json.loads(resp_data.decode("utf-8"))
            if not isinstance(data, dict):
                raise TypeError("Gemini response JSON was not an object")
            text = _extract_gemini_text(data, operation="group_chat_reply", model=self._model)
            _record_success()
            return text, count
        except GeminiEmptyResponseError:
            raise
        except (KeyError, IndexError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "Gemini group agent response parse failed",
                extra={
                    "operation": "group_chat_reply",
                    "model": self._model,
                    "error_type": exc.__class__.__name__,
                },
            )
            raise GeminiUnavailableError("Bad Gemini response encoding or shape") from None
