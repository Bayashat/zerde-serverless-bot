"""Pure formatting and bounded style for explicit questions; no stored knowledge."""

from collections.abc import Mapping
from typing import Any

from services.telegram_actor import actor_display_name, actor_sender_type, message_actor

CHAT_STYLE_TONES = {"concise", "professional", "friendly"}

# These pure compatibility fields preserve the explicit-provider request contract;
# they cannot enable retired behavior or load persisted settings.
CHAT_STYLE_LOW_CONFIDENCE_BEHAVIORS = {"cautious", "avoid_weak_memory", "none"}


DEFAULT_CHAT_STYLE_PROFILE: dict[str, Any] = {
    "tone": "concise",
    "max_default_sentences": 5,
    "max_proactive_sentences": 2,
    "allow_light_humor": False,
    "low_confidence_behavior": "cautious",
}


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _bool_setting(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def normalise_chat_style_profile(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a safe chat-level style profile for agent replies."""
    profile = dict(DEFAULT_CHAT_STYLE_PROFILE)
    if not isinstance(raw, Mapping):
        return profile

    tone = str(raw.get("tone") or "").strip().lower()
    if tone in CHAT_STYLE_TONES:
        profile["tone"] = tone

    profile["max_default_sentences"] = _bounded_int(
        raw.get("max_default_sentences"),
        default=profile["max_default_sentences"],
        minimum=1,
        maximum=8,
    )
    profile["max_proactive_sentences"] = _bounded_int(
        raw.get("max_proactive_sentences"),
        default=profile["max_proactive_sentences"],
        minimum=1,
        maximum=4,
    )
    profile["allow_light_humor"] = _bool_setting(
        raw.get("allow_light_humor"),
        default=profile["allow_light_humor"],
    )
    low_confidence_behavior = str(raw.get("low_confidence_behavior") or "").strip().lower()
    if low_confidence_behavior in CHAT_STYLE_LOW_CONFIDENCE_BEHAVIORS:
        profile["low_confidence_behavior"] = low_confidence_behavior
    return profile


def extract_message_text(message: dict[str, Any]) -> str:
    """Return visible text/caption for the current explicit request."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def format_message_reference(
    message: dict[str, Any],
    *,
    heading: str = "Original replied-to message",
    max_text_chars: int = 1600,
) -> str:
    """Format a Telegram message as compact quoted context for agent prompts."""
    if not isinstance(message, dict):
        return ""
    text = extract_message_text(message)
    if not text:
        return ""

    actor = message_actor(message)
    sender_type = actor_sender_type(actor)

    metadata: list[str] = []
    actor_id = actor.get("id") if actor else None
    if sender_type != "user":
        metadata.append(f"sender_type={sender_type}")
    elif actor_id is not None:
        metadata.append(f"user_id={actor_id}")
    username = (actor.get("username") or "").strip() if actor else ""
    if username:
        metadata.append(f"username=@{username}")
    name = actor_display_name(actor)
    if name:
        metadata.append(f"name={name[:80]}")
    message_id = message.get("message_id")
    if message_id is not None:
        metadata.append(f"message_id={message_id}")

    speaker = f"[speaker {' '.join(metadata)}]" if metadata else "[speaker unknown]"
    clipped_text = text[:max_text_chars]
    return f"{heading}:\n{speaker} {clipped_text}"
