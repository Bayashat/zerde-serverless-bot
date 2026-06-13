"""Ambient emoji reactions for ordinary group messages."""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from core.config import (
    AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD,
    AMBIENT_REACTIONS_ENABLED,
    AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY,
    AMBIENT_REACTIONS_MAX_PER_CHAT_PER_HOUR,
    AMBIENT_REACTIONS_MIN_GAP_PER_CHAT_SECONDS,
    AMBIENT_REACTIONS_MIN_GAP_PER_USER_SECONDS,
    AMBIENT_REACTIONS_SAMPLE_RATE,
    get_chat_lang,
)
from core.logger import LoggerAdapter, get_logger
from services.ai.ambient_reaction_classifier import (
    FallbackAmbientReactionClassifier,
    create_ambient_reaction_classifier,
)
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient
from services.telegram import TelegramClient
from services.telegram_actor import (
    actor_display_name,
    actor_sender_type,
    actor_username,
    is_linked_channel_discussion_post,
    message_actor,
)
from zerde_common.ai_errors import ZerdeProviderError

logger = LoggerAdapter(get_logger(__name__), {})

ALLOWED_AMBIENT_REACTION_EMOJIS: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀")
AMBIENT_REACTION_CATEGORIES: tuple[str, ...] = ("humor", "useful", "thoughtful", "warm", "interesting", "none")
MAX_PREVIOUS_CONTEXT_MESSAGES = 10
MAX_REPLY_CHAIN_DEPTH = 3
MAX_CONTEXT_MESSAGES_TOTAL = 15

_WORD_CHAR_RE = re.compile(r"[0-9A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё\u4e00-\u9fff]")
_WORD_TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яӘәҒғҚқҢңӨөҰұҮүҺһІіЁё\u4e00-\u9fff][\w+#._-]*")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", flags=re.IGNORECASE)
_MEDIA_KEYS = {
    "animation",
    "audio",
    "contact",
    "dice",
    "document",
    "game",
    "location",
    "photo",
    "poll",
    "sticker",
    "venue",
    "video",
    "video_note",
    "voice",
}
_ambient_classifier: FallbackAmbientReactionClassifier | None = None


@dataclass(frozen=True)
class AmbientReactionDecision:
    should_react: bool
    emoji: str | None
    confidence: float
    category: str
    reason: str


@dataclass(frozen=True)
class AmbientReactionRateLimit:
    allowed: bool
    reason: str = ""


@dataclass(frozen=True)
class AmbientReactionContext:
    previous_messages: tuple[dict[str, Any], ...]
    reply_chain: tuple[dict[str, Any], ...]
    current_message: dict[str, Any]


def _get_classifier() -> FallbackAmbientReactionClassifier | None:
    global _ambient_classifier
    if _ambient_classifier is None:
        _ambient_classifier = create_ambient_reaction_classifier()
    return _ambient_classifier


def _compact_text(text: str, *, limit: int) -> str:
    return " ".join((text or "").split())[:limit]


def _message_text(message: dict[str, Any]) -> str:
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def _linked_channel_reaction_text(message: dict[str, Any]) -> str:
    text = _message_text(message)
    if text:
        return text
    return "Official linked-channel media post without text caption."


def _looks_like_pure_link(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    without_urls = _URL_RE.sub("", stripped).strip(" \t\r\n.,;:!?()[]{}<>")
    if without_urls:
        return False
    return bool(_URL_RE.search(stripped))


def _looks_like_too_short_or_emoji_only(text: str) -> bool:
    compact = _compact_text(text, limit=500)
    if len(compact) < 12:
        return True
    if not _WORD_CHAR_RE.search(compact):
        return True
    words = _WORD_TOKEN_RE.findall(compact)
    return len(words) < 2 and len(compact) < 24


def is_ambient_reaction_eligible(update: dict[str, Any]) -> bool:
    """Return whether a Telegram update may be considered for ambient reaction sampling."""
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return False
    user = message.get("from") or {}
    if not isinstance(user, dict) or not user.get("id") or user.get("is_bot"):
        return False
    if is_linked_channel_discussion_post(message):
        return True
    if any(key in message for key in _MEDIA_KEYS):
        return False
    text = _message_text(message)
    if not text:
        return False
    stripped = text.strip()
    if _looks_like_too_short_or_emoji_only(stripped):
        return False
    if _looks_like_pure_link(stripped):
        return False
    return True


def _message_context_from_telegram(message: dict[str, Any], *, max_text_chars: int = 700) -> dict[str, Any] | None:
    if any(key in message for key in _MEDIA_KEYS) and not is_linked_channel_discussion_post(message):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        text = message.get("caption")
    if not isinstance(text, str) or not text.strip():
        return None
    actor = message_actor(message)
    sender_type = actor_sender_type(actor)
    item: dict[str, Any] = {
        "message_id": message.get("message_id"),
        "user_id": actor.get("id") if actor else None,
        "display_name": actor_display_name(actor) if actor else "",
        "sender_type": sender_type,
        "text": _compact_text(text, limit=max_text_chars),
    }
    username = actor_username(actor)
    if username:
        item["username"] = username
    if message.get("date") is not None:
        item["created_at"] = message.get("date")
    return item


def _reply_chain_payload(message: dict[str, Any]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    current = message.get("reply_to_message")
    depth = 0
    while isinstance(current, dict) and depth < MAX_REPLY_CHAIN_DEPTH:
        item = _message_context_from_telegram(current, max_text_chars=700)
        if item:
            chain.append(item)
        current = current.get("reply_to_message")
        depth += 1
    return chain


def build_ambient_reaction_task_payload(update: dict[str, Any]) -> dict[str, Any] | None:
    """Build the compact SQS payload for one eligible ambient reaction candidate."""
    if not is_ambient_reaction_eligible(update):
        return None
    message = update["message"]
    linked_channel_post = is_linked_channel_discussion_post(message)
    actor = message_actor(message)
    chat_id = message["chat"]["id"]
    username = actor_username(actor)
    payload: dict[str, Any] = {
        "update_id": update.get("update_id"),
        "chat_id": chat_id,
        "message_id": message["message_id"],
        "user_id": actor.get("id"),
        "display_name": actor_display_name(actor),
        "sender_type": actor_sender_type(actor),
        "text": _compact_text(
            _linked_channel_reaction_text(message) if linked_channel_post else _message_text(message), limit=1200
        ),
        "lang": get_chat_lang(chat_id),
        "force_reaction": linked_channel_post,
    }
    if username:
        payload["username"] = username
    if message.get("date"):
        payload["created_at"] = message.get("date")
    reply_chain = _reply_chain_payload(message)
    if reply_chain:
        payload["reply_chain"] = reply_chain
    return payload


def maybe_enqueue_ambient_reaction(
    *,
    repo: GroupMemoryRepository | None,
    update: dict[str, Any],
    sqs_repo: SQSClient | None,
    random_fn: Any = random.random,
) -> bool:
    """Sample and enqueue ambient reaction work without blocking normal webhook handling."""
    if not AMBIENT_REACTIONS_ENABLED or repo is None or sqs_repo is None:
        return False
    payload = build_ambient_reaction_task_payload(update)
    if not payload:
        return False
    if not payload.get("force_reaction") and (
        AMBIENT_REACTIONS_SAMPLE_RATE <= 0 or float(random_fn()) >= AMBIENT_REACTIONS_SAMPLE_RATE
    ):
        return False
    try:
        sqs_repo.send_ambient_reaction_task(**payload)
        return True
    except Exception:
        logger.exception(
            "Failed to queue ambient reaction task",
            extra={"chat_id": payload.get("chat_id"), "message_id": payload.get("message_id")},
        )
        return False


def _message_context_from_repo_item(item: dict[str, Any]) -> dict[str, Any] | None:
    text = str(item.get("text") or "").strip()
    if not text:
        return None
    result: dict[str, Any] = {
        "message_id": item.get("message_id"),
        "user_id": item.get("user_id"),
        "display_name": item.get("display_name") or item.get("username") or item.get("user_id") or "",
        "text": _compact_text(text, limit=700),
    }
    if item.get("username"):
        result["username"] = str(item["username"]).lstrip("@")
    if item.get("sender_type"):
        result["sender_type"] = str(item["sender_type"])[:80]
    if item.get("created_at") is not None:
        result["created_at"] = item.get("created_at")
    return result


def _is_previous_message(item: dict[str, Any], *, current_message_id: int, current_created_at: int | None) -> bool:
    try:
        message_id = int(item.get("message_id"))
    except (TypeError, ValueError):
        return False
    if message_id == current_message_id:
        return False
    if current_created_at is None:
        return True
    try:
        created_at = int(item.get("created_at") or 0)
    except (TypeError, ValueError):
        created_at = 0
    if created_at and created_at > current_created_at:
        return False
    if created_at == current_created_at and message_id > current_message_id:
        return False
    return True


def gather_ambient_reaction_context(
    *,
    repo: GroupMemoryRepository,
    chat_id: int | str,
    current_message_id: int,
    current_user_id: int | str,
    current_display_name: str,
    current_text: str,
    current_created_at: int | None = None,
    current_username: str | None = None,
    current_sender_type: str = "user",
    reply_chain: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> AmbientReactionContext:
    """Collect bounded recent and reply context for the classifier."""
    recent_items = repo.get_recent_messages(chat_id, limit=MAX_CONTEXT_MESSAGES_TOTAL + MAX_PREVIOUS_CONTEXT_MESSAGES)
    previous: list[dict[str, Any]] = []
    for item in recent_items:
        if not isinstance(item, dict):
            continue
        if not _is_previous_message(item, current_message_id=current_message_id, current_created_at=current_created_at):
            continue
        message_context = _message_context_from_repo_item(item)
        if message_context:
            previous.append(message_context)

    reply_items: list[dict[str, Any]] = []
    for item in list(reply_chain or [])[:MAX_REPLY_CHAIN_DEPTH]:
        if isinstance(item, dict) and str(item.get("text") or "").strip():
            copied = dict(item)
            copied["text"] = _compact_text(str(copied["text"]), limit=700)
            reply_items.append(copied)

    reply_message_ids = {str(item.get("message_id")) for item in reply_items if item.get("message_id") is not None}
    if reply_message_ids:
        previous = [item for item in previous if str(item.get("message_id")) not in reply_message_ids]

    space_for_previous = max(0, MAX_CONTEXT_MESSAGES_TOTAL - 1 - len(reply_items))
    previous = previous[-min(MAX_PREVIOUS_CONTEXT_MESSAGES, space_for_previous) :]
    current: dict[str, Any] = {
        "message_id": current_message_id,
        "user_id": str(current_user_id),
        "display_name": current_display_name,
        "sender_type": current_sender_type,
        "text": _compact_text(current_text, limit=1200),
    }
    if current_username:
        current["username"] = str(current_username).lstrip("@")
    if current_created_at is not None:
        current["created_at"] = current_created_at
    return AmbientReactionContext(
        previous_messages=tuple(previous),
        reply_chain=tuple(reply_items),
        current_message=current,
    )


def _format_context_message(item: dict[str, Any]) -> str:
    bits: list[str] = []
    sender_type = str(item.get("sender_type") or "").strip()
    if sender_type and sender_type != "user":
        bits.append(f"sender_type={sender_type[:80]}")
    elif item.get("user_id") is not None:
        bits.append(f"user_id={item['user_id']}")
    if item.get("username"):
        bits.append(f"username=@{str(item['username']).lstrip('@')}")
    name = str(item.get("display_name") or "").strip()
    if name:
        bits.append(f"name={name[:80]}")
    if item.get("message_id") is not None:
        bits.append(f"message_id={item['message_id']}")
    speaker = f"[speaker {' '.join(bits)}]" if bits else "[speaker unknown]"
    return f"{speaker} {str(item.get('text') or '').replace(chr(10), ' ')[:900]}"


def format_ambient_reaction_prompt_context(context: AmbientReactionContext) -> tuple[str, str, str]:
    previous = "\n".join(_format_context_message(item) for item in context.previous_messages)
    replies = "\n".join(
        f"[reply_depth={idx + 1}] {_format_context_message(item)}"
        for idx, item in enumerate(context.reply_chain[:MAX_REPLY_CHAIN_DEPTH])
    )
    current = _format_context_message(context.current_message)
    return previous, replies, current


def validate_ambient_reaction_decision(
    raw_output: str | dict[str, Any],
    *,
    confidence_threshold: float = AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD,
    allowed_emojis: tuple[str, ...] = ALLOWED_AMBIENT_REACTION_EMOJIS,
) -> AmbientReactionDecision | None:
    """Parse and strictly validate the classifier contract."""
    try:
        raw = json.loads(raw_output) if isinstance(raw_output, str) else raw_output
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None

    should_react = raw.get("should_react")
    if not isinstance(should_react, bool):
        return None
    confidence_raw = raw.get("confidence")
    if isinstance(confidence_raw, bool):
        return None
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        return None
    if confidence < 0 or confidence > 1:
        return None
    category = str(raw.get("category") or "none").strip().lower()[:80]
    if not category:
        return None
    reason = str(raw.get("reason") or "").strip()[:300]

    emoji = raw.get("emoji")
    if not should_react:
        if emoji is not None:
            return None
        return AmbientReactionDecision(False, None, confidence, "none", reason)

    if not isinstance(emoji, str) or emoji not in allowed_emojis:
        return None
    if confidence < confidence_threshold:
        return AmbientReactionDecision(False, None, confidence, category, reason or "Low confidence reaction signal.")
    return AmbientReactionDecision(True, emoji, confidence, category, reason)


def evaluate_ambient_reaction_rate_limit(
    events: list[dict[str, Any]],
    *,
    user_id: int | str,
    now: int,
    min_gap_per_chat_seconds: int = AMBIENT_REACTIONS_MIN_GAP_PER_CHAT_SECONDS,
    min_gap_per_user_seconds: int = AMBIENT_REACTIONS_MIN_GAP_PER_USER_SECONDS,
    max_per_chat_per_hour: int = AMBIENT_REACTIONS_MAX_PER_CHAT_PER_HOUR,
    max_per_chat_per_day: int = AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY,
) -> AmbientReactionRateLimit:
    """Evaluate cooldowns and per-chat reaction caps from recent event rows."""
    if max_per_chat_per_hour <= 0 or max_per_chat_per_day <= 0:
        return AmbientReactionRateLimit(False, "disabled_by_limit")
    user_id_str = str(user_id)
    hour_start = now - 60 * 60
    day_start = now - 24 * 60 * 60
    hour_count = 0
    day_count = 0
    for event in events:
        try:
            created_at = int(event.get("created_at") or 0)
        except (TypeError, ValueError):
            continue
        if created_at < day_start:
            continue
        day_count += 1
        if created_at >= hour_start:
            hour_count += 1
        if min_gap_per_chat_seconds > 0 and now - created_at < min_gap_per_chat_seconds:
            return AmbientReactionRateLimit(False, "chat_cooldown")
        if (
            min_gap_per_user_seconds > 0
            and str(event.get("user_id") or "") == user_id_str
            and now - created_at < min_gap_per_user_seconds
        ):
            return AmbientReactionRateLimit(False, "user_cooldown")
    if hour_count >= max_per_chat_per_hour:
        return AmbientReactionRateLimit(False, "chat_hourly_limit")
    if day_count >= max_per_chat_per_day:
        return AmbientReactionRateLimit(False, "chat_daily_limit")
    return AmbientReactionRateLimit(True)


def _parse_task_body(body: dict[str, Any]) -> dict[str, Any] | None:
    try:
        parsed = {
            "chat_id": int(body["chat_id"]),
            "message_id": int(body["message_id"]),
            "user_id": body["user_id"],
            "text": str(body["text"]).strip(),
            "display_name": str(body.get("display_name") or body.get("username") or body["user_id"])[:80],
            "username": str(body.get("username") or "").lstrip("@") or None,
            "sender_type": str(body.get("sender_type") or "user")[:80],
            "lang": str(body.get("lang") or get_chat_lang(body["chat_id"])),
            "created_at": int(body["created_at"]) if body.get("created_at") is not None else None,
            "reply_chain": body.get("reply_chain") if isinstance(body.get("reply_chain"), list) else [],
            "force_reaction": bool(body.get("force_reaction")),
        }
    except (KeyError, TypeError, ValueError):
        return None
    if not parsed["text"]:
        return None
    return parsed


def process_ambient_reaction_task(
    *,
    repo: GroupMemoryRepository | None,
    bot: TelegramClient,
    body: dict[str, Any],
) -> bool:
    """Classify and possibly react to one sampled ambient reaction candidate."""
    parsed = _parse_task_body(body)
    if not AMBIENT_REACTIONS_ENABLED or repo is None or not parsed:
        return False
    chat_id = parsed["chat_id"]
    message_id = parsed["message_id"]
    user_id = parsed["user_id"]
    text = parsed["text"]
    force_reaction = bool(parsed["force_reaction"])
    if not force_reaction and (_looks_like_too_short_or_emoji_only(text) or _looks_like_pure_link(text)):
        return False

    classifier = _get_classifier()
    if classifier is None and not force_reaction:
        logger.info(
            "Ambient reaction skipped because no AI classifier provider is configured", extra={"chat_id": chat_id}
        )
        return False

    now = int(time.time())
    try:
        if not force_reaction:
            events = repo.get_recent_ambient_reactions(
                chat_id,
                since_epoch=now - 24 * 60 * 60,
                limit=max(AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY + 10, 50),
            )
            rate = evaluate_ambient_reaction_rate_limit(events, user_id=user_id, now=now)
            if not rate.allowed:
                logger.info(
                    "Ambient reaction skipped by rate limit",
                    extra={"chat_id": chat_id, "message_id": message_id, "reason": rate.reason},
                )
                return False
        context = gather_ambient_reaction_context(
            repo=repo,
            chat_id=chat_id,
            current_message_id=message_id,
            current_user_id=user_id,
            current_display_name=parsed["display_name"],
            current_text=text,
            current_created_at=parsed["created_at"],
            current_username=parsed["username"],
            current_sender_type=parsed["sender_type"],
            reply_chain=parsed["reply_chain"],
        )
        previous_context, reply_context, current_context = format_ambient_reaction_prompt_context(context)
        provider_name = "forced_fallback"
        decision: AmbientReactionDecision | None = None
        if classifier is not None:
            try:
                raw_decision, provider_name = classifier.ambient_reaction_decision(
                    current_message=current_context,
                    previous_context=previous_context,
                    reply_context=reply_context,
                    allowed_emojis=ALLOWED_AMBIENT_REACTION_EMOJIS,
                    lang=parsed["lang"],
                )
                decision = validate_ambient_reaction_decision(
                    raw_decision,
                    confidence_threshold=0.0 if force_reaction else AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD,
                )
            except ZerdeProviderError:
                if not force_reaction:
                    raise
                logger.info(
                    "Forced ambient reaction classifier unavailable; using fallback emoji",
                    extra={"chat_id": chat_id, "message_id": message_id},
                )
        if force_reaction and (decision is None or not decision.should_react or not decision.emoji):
            decision = AmbientReactionDecision(
                True,
                "👀",
                1.0,
                "interesting",
                "Forced linked-channel post reaction fallback.",
            )
        if decision is None or not decision.should_react or not decision.emoji:
            logger.info(
                "Ambient reaction classifier skipped message",
                extra={"chat_id": chat_id, "message_id": message_id, "provider": provider_name},
            )
            return False
        bot.set_message_reaction(chat_id, message_id, decision.emoji)
        repo.record_ambient_reaction(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            emoji=decision.emoji,
            category=decision.category,
            confidence=decision.confidence,
            created_at=now,
        )
        logger.info(
            "Ambient reaction set",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
                "emoji": decision.emoji,
                "category": decision.category,
                "confidence": decision.confidence,
                "provider": provider_name,
            },
        )
        return True
    except ZerdeProviderError as exc:
        logger.info(
            "Ambient reaction classifier unavailable",
            extra={"chat_id": chat_id, "message_id": message_id, "error_type": exc.__class__.__name__},
        )
        return False
    except Exception as exc:
        logger.warning(
            "Ambient reaction failed safely",
            extra={"chat_id": chat_id, "message_id": message_id, "error": str(exc)[:300]},
            exc_info=True,
        )
        return False
