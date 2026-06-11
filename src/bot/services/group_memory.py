"""High-level helpers for observing Telegram updates into group memory."""

from __future__ import annotations

import re
from typing import Any

from core.config import GROUP_MEMORY_ENABLED, GROUP_MEMORY_RECENT_LIMIT
from core.logger import LoggerAdapter, get_logger
from services.repositories.group_memory import GroupMemoryRepository

logger = LoggerAdapter(get_logger(__name__), {})

_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{3,32})")


def extract_message_text(message: dict[str, Any]) -> str:
    """Return visible text/caption worth storing for group context."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def display_name(user: dict[str, Any]) -> str:
    """Build a compact display name for prompts and memory profiles."""
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    username = (user.get("username") or "").strip()
    full = " ".join(part for part in (first, last) if part)
    if full:
        return full[:80]
    if username:
        return f"@{username}"[:80]
    return str(user.get("id") or "Unknown")


def is_storable_group_message(update: dict[str, Any]) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat = message.get("chat") or {}
    if chat.get("type") not in {"group", "supergroup"}:
        return False
    user = message.get("from") or {}
    if user.get("is_bot"):
        return False
    text = extract_message_text(message)
    return bool(text and not text.startswith("/"))


def observe_update(repo: GroupMemoryRepository | None, update: dict[str, Any]) -> None:
    """Persist a human group message when global and per-chat memory are enabled."""
    if not GROUP_MEMORY_ENABLED or repo is None or not is_storable_group_message(update):
        return

    message = update["message"]
    chat_id = message["chat"]["id"]
    if not repo.is_memory_enabled(chat_id):
        return

    user = message.get("from") or {}
    user_id = user.get("id")
    message_id = message.get("message_id")
    text = extract_message_text(message)
    if not all([chat_id, user_id, message_id, text]):
        return

    try:
        repo.store_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            display_name=display_name(user),
            username=user.get("username"),
            text=text,
            created_at=message.get("date"),
        )
        logger.debug("Stored group memory message", extra={"chat_id": chat_id, "message_id": message_id})
    except Exception:
        logger.exception("Failed to store group memory message", extra={"chat_id": chat_id, "message_id": message_id})


def format_recent_context(repo: GroupMemoryRepository, chat_id: int | str, *, limit: int | None = None) -> str:
    """Render recent messages as compact prompt context.

    Speaker metadata is intentionally explicit so the group agent can separate
    "Alice said this about Bob" from "Bob said this about himself".
    """
    messages = repo.get_recent_messages(chat_id, limit=limit or GROUP_MEMORY_RECENT_LIMIT)
    lines: list[str] = []
    for item in messages:
        name = str(item.get("display_name") or item.get("username") or item.get("user_id") or "Unknown")
        username = str(item.get("username") or "").strip()
        user_id = str(item.get("user_id") or "").strip()
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if text:
            speaker_bits = []
            if user_id:
                speaker_bits.append(f"user_id={user_id}")
            if username:
                speaker_bits.append(f"username=@{username.lstrip('@')}")
            speaker_bits.append(f"name={name[:80]}")
            lines.append(f"[speaker {' '.join(speaker_bits)}] {text[:700]}")
    return "\n".join(lines)


def extract_mentioned_usernames(text: str, *, ignore: set[str] | None = None) -> set[str]:
    """Return Telegram usernames mentioned in text, excluding known bot handles."""
    ignored = {item.lower().lstrip("@") for item in (ignore or set()) if item}
    usernames: set[str] = set()
    for match in _USERNAME_RE.finditer(text or ""):
        username = match.group(1).lower()
        if username not in ignored:
            usernames.add(username)
    return usernames


def _profile_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_topic_counts(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    counts: list[tuple[str, int]] = []
    for key, raw_count in value.items():
        term = str(key or "").strip()
        count = _profile_count(raw_count)
        if term and count > 0:
            counts.append((term, count))
    if not counts:
        return ""
    counts.sort(key=lambda item: (-item[1], item[0]))
    return ", ".join(term for term, _ in counts[:10])


def _format_recent_samples(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    samples: list[str] = []
    for item in value:
        text = str(item or "").replace("\n", " ").strip()
        if text:
            samples.append(text[:220])
    return samples[-5:]


def format_user_profile_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    user_text: str,
    ignored_usernames: set[str] | None = None,
) -> str:
    """Render trusted target-user profile context from the target's own messages."""
    usernames = extract_mentioned_usernames(user_text, ignore=ignored_usernames)
    profiles = repo.get_user_profiles_by_usernames(chat_id, usernames)
    if not profiles:
        return ""

    lines = ["Trusted target-user profiles derived only from each user's own stored messages:"]
    for profile in profiles:
        username = str(profile.get("username") or "").lstrip("@")
        display = str(profile.get("display_name") or username or profile.get("user_id") or "Unknown")
        message_count = _profile_count(profile.get("message_count"))
        header_bits = [f"name={display[:80]}"]
        if username:
            header_bits.append(f"username=@{username}")
        if profile.get("user_id"):
            header_bits.append(f"user_id={profile['user_id']}")
        if message_count:
            header_bits.append(f"own_messages={message_count}")
        lines.append(f"- [{' '.join(header_bits)}]")

        topics = _format_topic_counts(profile.get("topic_counts"))
        if topics:
            lines.append(f"  own_topic_terms: {topics}")

        samples = _format_recent_samples(profile.get("recent_samples"))
        if samples:
            lines.append("  recent_own_messages:")
            for sample in samples:
                lines.append(f"  - {sample}")

    return "\n".join(lines)
