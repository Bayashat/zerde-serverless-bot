"""Gemini REST API client for group-agent replies and memory summaries.

Rate-limit tracking uses an atomic DynamoDB counter (RPD) shared
across all Lambda invocations and chat groups. The "day" matches
Gemini/Google: calendar date in America/Los_Angeles (midnight PT reset).

Group-agent commands that may call Gemini are queued through SQS so the Telegram
webhook can return quickly and avoid duplicate update retries.
"""

import json
import time
from dataclasses import dataclass
from typing import Any

import urllib3
from core.config import GEMINI_API_BASE, GEMINI_MODEL, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
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
        self._model = GEMINI_MODEL
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
            "Decide the answer style from the user's wording and the replied-to context: "
            "for IT terms or technical concepts, give a clear technical explanation; "
            "for questions about a replied-to group message, explain the message in context; "
            "for questions about whether someone is joking, being sarcastic, or implying something, use the "
            "recent group context and answer carefully without overclaiming; "
            "if the user explicitly asks for a harsher, cynical, or playful tone, you may match that request "
            "briefly, but do not use a fixed angry persona by default; "
            "for normal questions, stay natural, concise, and conversational like a group member. "
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
        long_term_memory_context: str = "",
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
            "Trusted long-term group memory:\n"
            f"{long_term_memory_context or '(no long-term memory available)'}\n\n"
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
                "long_term_memory_chars": len(long_term_memory_context),
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

    def group_daily_summary(
        self,
        *,
        summary_date: str,
        messages_context: str,
        long_term_memory_context: str = "",
        lang: str = "kk",
    ) -> tuple[dict[str, Any], int]:
        """Summarize one group/day into structured memory fields."""
        if _circuit_is_open():
            logger.warning("Gemini circuit open, skipping daily summary", extra={"model": self._model})
            raise GeminiUnavailableError("Gemini circuit open")

        count, within_limit = self._rate_repo.increment_and_check()
        if not within_limit:
            logger.warning("Gemini RPD limit reached (daily summary)", extra={"count": count, "limit": self.rpd_limit})
            raise GeminiRPDExhaustedError(f"RPD limit reached: {count}/{self.rpd_limit}")

        system_prompt = (
            "You compress one Telegram group day into trustworthy memory for ZerdeBot. "
            "Summarize only what is directly supported by the messages. Do not infer private traits, secrets, "
            "medical, financial, identity, or contact details. Preserve useful context: events, decisions, "
            "recurring topics, harmless inside jokes, active participants, and tension points if any. "
            "Return compact JSON with keys: summary (string), topics (array of strings), "
            "notable_events (array), inside_jokes (array), active_participants (array), tension_points (array)."
        )
        generation_config: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": 900,
            "responseMimeType": "application/json",
        }
        thinking_config = _thinking_config_for_model(self._model)
        if thinking_config is not None:
            generation_config["thinkingConfig"] = thinking_config

        prompt = (
            f"Preferred language code: {lang}\n"
            f"Summary date: {summary_date}\n\n"
            "Already extracted long-term memories for this period:\n"
            f"{long_term_memory_context or '(none)'}\n\n"
            "Messages, oldest to newest:\n"
            f"{messages_context}\n\n"
            "Create the daily memory summary JSON."
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
            "Gemini daily summary request started",
            extra={
                "model": self._model,
                "lang": lang,
                "summary_date": summary_date,
                "messages_context_chars": len(messages_context),
                "long_term_memory_chars": len(long_term_memory_context),
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
            summary = json.loads(text)
            _record_success()
            return summary if isinstance(summary, dict) else {}, count
        except (KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            raise GeminiUnavailableError(f"Bad Gemini daily summary response: {exc}") from exc
