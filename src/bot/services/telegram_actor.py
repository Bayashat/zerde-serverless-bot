"""Telegram message actor helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.config import TELEGRAM_CHANNEL_POST_ACTOR_USER_ID


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def is_linked_channel_discussion_post(message: Mapping[str, Any] | dict[str, Any]) -> bool:
    """Return True for linked channel posts mirrored into a discussion supergroup."""
    if not isinstance(message, Mapping):
        return False
    if message.get("is_automatic_forward") is True:
        return True
    sender = _mapping(message.get("from"))
    sender_chat = _mapping(message.get("sender_chat"))
    return sender.get("id") == TELEGRAM_CHANNEL_POST_ACTOR_USER_ID and sender_chat.get("type") == "channel"


def message_actor(message: Mapping[str, Any] | dict[str, Any]) -> Mapping[str, Any]:
    """Return the best actor for a Telegram message.

    Linked channel discussion posts arrive with ``from.id=777000`` and the real
    channel identity in ``sender_chat``. Prefer the channel identity there so
    prompts, rate limits, and short-term memory do not attribute every mirrored
    post to Telegram's synthetic actor.
    """
    if not isinstance(message, Mapping):
        return {}
    sender_chat = _mapping(message.get("sender_chat"))
    if is_linked_channel_discussion_post(message) and sender_chat:
        return sender_chat
    sender = _mapping(message.get("from"))
    if sender:
        return sender
    return sender_chat


def actor_display_name(actor: Mapping[str, Any] | dict[str, Any]) -> str:
    """Build a compact display name for a Telegram user or chat actor."""
    actor = _mapping(actor)
    title = str(actor.get("title") or "").strip()
    if title:
        return title[:80]
    first = str(actor.get("first_name") or "").strip()
    last = str(actor.get("last_name") or "").strip()
    username = str(actor.get("username") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    if full:
        return full[:80]
    if username:
        return f"@{username}"[:80]
    return str(actor.get("id") or "Unknown")


def actor_username(actor: Mapping[str, Any] | dict[str, Any]) -> str | None:
    username = str(_mapping(actor).get("username") or "").strip().lstrip("@")
    return username or None


def actor_sender_type(actor: Mapping[str, Any] | dict[str, Any]) -> str:
    actor = _mapping(actor)
    actor_type = str(actor.get("type") or "").strip().lower()
    if actor_type:
        return actor_type[:80]
    return "user"
