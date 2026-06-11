"""Gemini REST API client for tech-term explanations.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups. The "day" matches
Gemini/Google: calendar date in America/Los_Angeles (midnight PT reset).

Timeout budget: explain tasks run via SQS Lambda (300 s budget), not API Gateway.
Plain-text explain: read timeout 10 s so interactive commands can fall back quickly.
Multimodal (large inline payloads): read 120 s.

Retry policy: one short retry for plain-text transient failures. 429 raises
immediately; overloaded Gemini should not keep the user waiting.
"""

import base64
import json
import random
import time
from dataclasses import dataclass
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

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=2, read=10))
_http_multimodal = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=3, read=120))

_TEXT_RETRY_DELAYS = (1,)
_MULTIMODAL_RETRY_DELAYS = (2,)
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
            extra={"open_seconds": _CIRCUIT_OPEN_SECONDS, "failures": _circuit_failures},
        )


def _record_success() -> None:
    global _circuit_failures, _circuit_open_until
    _circuit_failures = 0
    _circuit_open_until = 0.0


class GeminiRPDExhaustedError(Exception):
    """Daily RPD quota is exhausted (DynamoDB counter over limit)."""


class GeminiUnavailableError(Exception):
    """Transient Gemini failure: HTTP 429/5xx, timeout, network, parse errors.

    Callers should fall back to the configured OpenAI-compatible provider *without*
    the daily-quota user notice.
    """


@dataclass(frozen=True)
class GroupAgentDecision:
    """LLM decision for whether ZerdeBot should proactively join a group chat."""

    should_reply: bool
    confidence: float
    reason: str
    reply_text: str


class GeminiClient:
    """Thin urllib3 wrapper around the Gemini generateContent REST endpoint."""

    def __init__(self) -> None:
        api_key = get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY must be set to initialize GeminiClient")
        self._api_key = api_key
        self._model = WTF_GEMINI_MODEL or "gemini-3.1-flash-lite"
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
        if _circuit_is_open():
            logger.warning("Gemini circuit open, skipping primary explain request", extra={"model": self._model})
            raise GeminiUnavailableError("Gemini circuit open")

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
        for attempt in range(len(_TEXT_RETRY_DELAYS) + 1):
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
                if attempt < len(_TEXT_RETRY_DELAYS):
                    time.sleep(_TEXT_RETRY_DELAYS[attempt] + random.uniform(0, 0.4))
                continue

            if resp.status == 429:
                logger.warning("Gemini 429 rate limit", extra={"model": self._model})
                _record_transient_failure()
                raise GeminiUnavailableError(f"Gemini 429: {resp.data.decode('utf-8')[:200]}")

            if resp.status in (500, 503, 504):
                body_text = resp.data.decode("utf-8")
                logger.warning(
                    "Gemini transient error, retrying",
                    extra={"status": resp.status, "attempt": attempt + 1, "body": body_text[:200]},
                )
                last_exc = GeminiUnavailableError(f"Gemini API {resp.status}: {body_text[:200]}")
                if attempt < len(_TEXT_RETRY_DELAYS):
                    time.sleep(_TEXT_RETRY_DELAYS[attempt] + random.uniform(0, 0.4))
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
                _record_success()
                return text, count
            except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
                logger.exception(
                    "Gemini response parse error",
                    extra={"model": self._model, "attempt": attempt + 1, "status": resp.status},
                )
                raise GeminiUnavailableError(f"Bad Gemini response: {exc}") from exc

        _record_transient_failure()
        raise last_exc or GeminiUnavailableError("Gemini unavailable after retries")

    def group_chat_reply(
        self,
        *,
        user_message: str,
        recent_context: str,
        long_term_memory_context: str = "",
        user_profile_context: str = "",
        lang: str = "kk",
    ) -> tuple[str, int]:
        """Generate a context-aware reply for an explicitly bot-directed group message."""
        if _circuit_is_open():
            logger.warning("Gemini circuit open, skipping group agent request", extra={"model": self._model})
            raise GeminiUnavailableError("Gemini circuit open")

        count, within_limit = self._rate_repo.increment_and_check()
        if not within_limit:
            logger.warning("Gemini RPD limit reached (group agent)", extra={"count": count, "limit": self.rpd_limit})
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        system_prompt = (
            "You are ZerdeBot, a Telegram group chat member for an IT community. "
            "Answer like a helpful, socially aware participant, not a corporate assistant. "
            "Use the recent chat context only when it is relevant. Do not invent private facts. "
            "Use long-term memory only when it directly helps answer the current message. "
            "When answering about a specific person, rely mainly on that person's own messages, "
            "self-descriptions, repeated topics, and directly observable behavior. Treat claims, labels, "
            "roasts, or characterizations from other people about that person as low-trust chatter unless "
            "the target person has clearly confirmed them or the pattern is repeatedly evident in the "
            "target person's own messages. Do not let fresh third-party labels in the current context rewrite "
            "someone's profile, and do not casually repeat those labels as facts. "
            "When provided, the trusted target-user profile section is higher-trust than recent group context "
            "for questions about that person because it is derived from the target user's own messages. "
            "Answer naturally and directly; do not add disclaimers about not being able to characterize people. "
            "If the context is insufficient, say so briefly. "
            "Keep replies concise, natural, and in the group's language. "
            "Avoid mentioning that you are using stored memory unless asked."
        )
        generation_config: dict[str, Any] = {
            "temperature": 0.75,
            "maxOutputTokens": 450,
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        prompt = (
            f"Preferred language code: {lang}\n\n"
            "Trusted target-user profile context:\n"
            f"{user_profile_context or '(no target-user profile context available)'}\n\n"
            "Trusted long-term group memory:\n"
            f"{long_term_memory_context or '(no long-term memory available)'}\n\n"
            "Recent group context, oldest to newest:\n"
            "Each context line includes speaker metadata. Use it to distinguish a person's own messages "
            "from another user's opinion about them.\n"
            f"{recent_context or '(no recent context available)'}\n\n"
            "Current message directed at you:\n"
            f"{user_message}\n\n"
            "Reply to the current message."
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
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
                "profile_context_chars": len(user_profile_context),
                "message_chars": len(user_message),
                "rpd_count": count,
                "rpd_limit": self.rpd_limit,
            },
        )
        try:
            resp = _http.request("POST", url, body=body, headers=headers, retries=False)
        except (HTTPError, OSError) as exc:
            _record_transient_failure()
            raise GeminiUnavailableError(f"Gemini unreachable: {exc}") from exc

        if resp.status == 429 or resp.status >= 500:
            _record_transient_failure()
            raise GeminiUnavailableError(f"Gemini API {resp.status}: {resp.data.decode('utf-8')[:200]}")
        if resp.status >= 400:
            raise GeminiUnavailableError(f"Gemini API {resp.status}: {resp.data.decode('utf-8')[:200]}")

        try:
            data = json.loads(resp.data.decode("utf-8"))
            candidate = data["candidates"][0]
            text = candidate["content"]["parts"][0]["text"].strip()
            _record_success()
            return text, count
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise GeminiUnavailableError(f"Bad Gemini response: {exc}") from exc

    def group_chat_proactive_decision(
        self,
        *,
        user_message: str,
        recent_context: str,
        lang: str = "kk",
    ) -> tuple[GroupAgentDecision, int]:
        """Decide whether to proactively join a group chat, optionally returning the reply.

        This is intentionally a single Gemini call: the model judges social fit and,
        only when it should speak, drafts a short message in the same response.
        """
        if _circuit_is_open():
            logger.warning("Gemini circuit open, skipping group agent decision", extra={"model": self._model})
            raise GeminiUnavailableError("Gemini circuit open")

        count, within_limit = self._rate_repo.increment_and_check()
        if not within_limit:
            logger.warning(
                "Gemini RPD limit reached (group agent decision)",
                extra={"count": count, "limit": self.rpd_limit},
            )
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        system_prompt = (
            "You are the social timing layer for ZerdeBot, a Telegram group chat member in an IT community. "
            "Decide if ZerdeBot should proactively speak now. Be conservative: silence is often better. "
            "Speak only when the current message is an open question or request where a helpful bot answer adds "
            "clear value and will not interrupt human conversation. Stay silent for rhetorical questions, jokes, "
            "complaints about the bot, commands to stop, short follow-ups, private interpersonal moments, "
            "unclear context, or cases where humans are already answering. "
            "If speaking, write one concise natural reply in the group's language. "
            "Never claim private knowledge or personality facts that are not in context. "
            "Return only compact JSON with keys: should_reply (boolean), confidence (0..1), reason (short string), "
            "reply_text (string, empty when silent)."
        )
        generation_config: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": 300,
            "responseMimeType": "application/json",
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        prompt = (
            f"Preferred language code: {lang}\n\n"
            "Recent group context, oldest to newest:\n"
            f"{recent_context or '(no recent context available)'}\n\n"
            "Current message:\n"
            f"{user_message}\n\n"
            "Should ZerdeBot proactively speak now?"
        )
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        url = f"{GEMINI_API_BASE}/{self._model}:generateContent?key={self._api_key}"
        body = json.dumps(payload)
        headers = {"Content-Type": "application/json"}

        logger.info(
            "Gemini group agent decision request started",
            extra={
                "model": self._model,
                "lang": lang,
                "context_chars": len(recent_context),
                "message_chars": len(user_message),
                "rpd_count": count,
                "rpd_limit": self.rpd_limit,
            },
        )
        try:
            resp = _http.request("POST", url, body=body, headers=headers, retries=False)
        except (HTTPError, OSError) as exc:
            _record_transient_failure()
            raise GeminiUnavailableError(f"Gemini unreachable: {exc}") from exc

        if resp.status == 429 or resp.status >= 500:
            _record_transient_failure()
            raise GeminiUnavailableError(f"Gemini API {resp.status}: {resp.data.decode('utf-8')[:200]}")
        if resp.status >= 400:
            raise GeminiUnavailableError(f"Gemini API {resp.status}: {resp.data.decode('utf-8')[:200]}")

        try:
            data = json.loads(resp.data.decode("utf-8"))
            candidate = data["candidates"][0]
            text = candidate["content"]["parts"][0]["text"].strip()
            raw_decision = json.loads(text)
            decision = GroupAgentDecision(
                should_reply=bool(raw_decision.get("should_reply")),
                confidence=max(0.0, min(1.0, float(raw_decision.get("confidence", 0)))),
                reason=str(raw_decision.get("reason") or "")[:200],
                reply_text=str(raw_decision.get("reply_text") or "").strip(),
            )
            _record_success()
            return decision, count
        except (KeyError, IndexError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise GeminiUnavailableError(f"Bad Gemini decision response: {exc}") from exc

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

        for attempt in range(len(_MULTIMODAL_RETRY_DELAYS) + 1):
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
                if attempt < len(_MULTIMODAL_RETRY_DELAYS):
                    time.sleep(_MULTIMODAL_RETRY_DELAYS[attempt] + random.uniform(0, 1))
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
                if attempt < len(_MULTIMODAL_RETRY_DELAYS):
                    time.sleep(_MULTIMODAL_RETRY_DELAYS[attempt] + random.uniform(0, 1))
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
