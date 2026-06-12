"""High-level helpers for observing Telegram updates into group memory."""

from __future__ import annotations

import re
from typing import Any

from core.config import (
    AGENT_BOT_ID,
    AGENT_BOT_USERNAME,
    GROUP_MEMORY_DAILY_SUMMARY_DAYS,
    GROUP_MEMORY_ENABLED,
    GROUP_MEMORY_RECENT_LIMIT,
)
from core.logger import LoggerAdapter, get_logger
from services.bot_identity import is_self_bot_user
from services.memory_safety import is_memory_learning_safe, is_profile_context_value_safe
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.sqs import SQSClient

logger = LoggerAdapter(get_logger(__name__), {})

_USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{3,32})")
_RELEVANCE_TERM_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{2,}", re.IGNORECASE)
_RELEVANCE_STOPWORDS = {
    "about",
    "and",
    "any",
    "are",
    "bot",
    "chat",
    "for",
    "from",
    "how",
    "the",
    "this",
    "what",
    "who",
    "why",
    "zerde",
    "бот",
    "бро",
    "его",
    "как",
    "кто",
    "меня",
    "нету",
    "про",
    "что",
    "чат",
    "это",
    "бар",
    "бір",
    "деп",
    "кім",
    "мен",
    "неге",
    "не",
    "ол",
    "осы",
    "сол",
    "үшін",
    "什么",
    "怎么",
    "这个",
}


def extract_message_text(message: dict[str, Any]) -> str:
    """Return visible text/caption worth storing for group context."""
    text = message.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    caption = message.get("caption")
    if isinstance(caption, str) and caption.strip():
        return caption.strip()
    return ""


def _message_has_mention(message: dict[str, Any], text: str) -> bool:
    if _USERNAME_RE.search(text):
        return True
    for field in ("entities", "caption_entities"):
        entities = message.get(field)
        if not isinstance(entities, list):
            continue
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if entity.get("type") in {"mention", "text_mention"}:
                return True
    return False


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

    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    sender_chat = message.get("sender_chat") if isinstance(message.get("sender_chat"), dict) else {}
    actor = sender or sender_chat

    metadata: list[str] = []
    actor_id = actor.get("id")
    if actor_id is not None:
        metadata.append(f"user_id={actor_id}")
    username = (actor.get("username") or "").strip()
    if username:
        metadata.append(f"username=@{username}")
    name = (actor.get("title") or "").strip() if sender_chat and not sender else display_name(actor)
    if name:
        metadata.append(f"name={name[:80]}")
    message_id = message.get("message_id")
    if message_id is not None:
        metadata.append(f"message_id={message_id}")

    speaker = f"[speaker {' '.join(metadata)}]" if metadata else "[speaker unknown]"
    clipped_text = text[:max_text_chars]
    return f"{heading}:\n{speaker} {clipped_text}"


def _reply_metadata(message: dict[str, Any]) -> dict[str, Any]:
    reply = message.get("reply_to_message")
    if not isinstance(reply, dict):
        return {}

    metadata: dict[str, Any] = {}
    reply_message_id = reply.get("message_id")
    if reply_message_id is not None:
        metadata["reply_to_message_id"] = reply_message_id

    sender = reply.get("from") if isinstance(reply.get("from"), dict) else {}
    sender_chat = reply.get("sender_chat") if isinstance(reply.get("sender_chat"), dict) else {}
    if sender:
        sender_id = sender.get("id")
        if sender_id is not None:
            metadata["reply_to_user_id"] = sender_id
        username = sender.get("username")
        if username:
            metadata["reply_to_sender_username"] = str(username).lstrip("@")[:160]
        name = display_name(sender)
        if name:
            metadata["reply_to_sender_name"] = name[:160]
        metadata["reply_to_sender_type"] = "user"
        metadata["reply_to_bot"] = bool(sender.get("is_bot"))
        metadata["reply_to_self_bot"] = is_self_bot_user(
            sender,
            bot_id=AGENT_BOT_ID,
            bot_username=AGENT_BOT_USERNAME,
        )
    elif sender_chat:
        sender_id = sender_chat.get("id")
        if sender_id is not None:
            metadata["reply_to_sender_id"] = sender_id
        username = sender_chat.get("username")
        if username:
            metadata["reply_to_sender_username"] = str(username).lstrip("@")[:160]
        title = sender_chat.get("title")
        if title:
            metadata["reply_to_sender_name"] = str(title)[:160]
        sender_type = sender_chat.get("type")
        metadata["reply_to_sender_type"] = str(sender_type or "sender_chat")[:80]
        metadata["reply_to_bot"] = False
        metadata["reply_to_self_bot"] = False

    root_message_id = None
    nested_reply = reply.get("reply_to_message")
    if isinstance(nested_reply, dict):
        root_message_id = nested_reply.get("message_id")
    if root_message_id is None:
        root_message_id = reply.get("message_thread_id") or message.get("message_thread_id")
    if root_message_id is not None:
        metadata["thread_root_message_id"] = root_message_id

    message_thread_id = message.get("message_thread_id")
    if message_thread_id is not None:
        metadata["message_thread_id"] = message_thread_id

    return metadata


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


def observe_update(
    repo: GroupMemoryRepository | None,
    update: dict[str, Any],
    *,
    sqs_repo: SQSClient | None = None,
) -> None:
    """Persist recent context and enqueue long-term processing for opted-in group messages."""
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
        sender_name = display_name(user)
        username = user.get("username")
        stored = repo.store_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            display_name=sender_name,
            username=username,
            text=text,
            created_at=message.get("date"),
            reply_metadata=_reply_metadata(message),
            skip_if_exists=True,
        )
        logger.debug("Stored group memory message", extra={"chat_id": chat_id, "message_id": message_id})
        if stored and sqs_repo:
            sqs_repo.send_group_memory_task(
                chat_id=chat_id,
                message_id=message_id,
                user_id=user_id,
                display_name=sender_name,
                username=username,
                text=text,
                created_at=message.get("date"),
                is_reply=bool(message.get("reply_to_message")),
                has_mention=_message_has_mention(message, text),
            )
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
        if text and not is_memory_learning_safe(text):
            continue
        if text:
            speaker_bits = []
            if user_id:
                speaker_bits.append(f"user_id={user_id}")
            if username:
                speaker_bits.append(f"username=@{username.lstrip('@')}")
            speaker_bits.append(f"name={name[:80]}")
            lines.append(f"[speaker {' '.join(speaker_bits)}] {text[:700]}")
    return "\n".join(lines)


def _relevance_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for raw in _RELEVANCE_TERM_RE.findall((text or "").lower()):
        term = raw.lstrip("@")
        if term and term not in _RELEVANCE_STOPWORDS and not term.isdigit():
            terms.add(term)
    return terms


def _memory_matches_query(item: dict[str, Any], query_terms: set[str]) -> bool:
    if not query_terms:
        return True
    fields = [
        item.get("summary"),
        item.get("text"),
        item.get("topics"),
        item.get("notable_events"),
        item.get("inside_jokes"),
        item.get("tension_points"),
        item.get("display_name"),
        item.get("username"),
    ]
    searchable = " ".join(
        str(part) for value in fields for part in (value if isinstance(value, list) else [value]) if part
    ).lower()
    return any(term in searchable for term in query_terms)


def format_long_term_memory_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    limit: int = 12,
    query_text: str | None = None,
) -> str:
    """Render recent important memories extracted by the async memory processor."""
    daily_summaries = repo.get_recent_daily_summaries(chat_id, limit=GROUP_MEMORY_DAILY_SUMMARY_DAYS)
    memories = repo.get_recent_long_term_memories(chat_id, limit=limit)
    query_terms = _relevance_terms(query_text or "")
    if query_text is not None and not query_terms:
        return ""
    lines: list[str] = []
    for item in daily_summaries:
        if not _memory_matches_query(item, query_terms):
            continue
        summary_date = str(item.get("summary_date") or "").strip()
        summary = str(item.get("summary") or "").replace("\n", " ").strip()
        topics = item.get("topics") if isinstance(item.get("topics"), list) else []
        topic_text = ", ".join(
            str(topic) for topic in topics[:8] if topic and is_profile_context_value_safe(str(topic))
        )
        if summary and is_memory_learning_safe(summary):
            topic_suffix = f" topics={topic_text}" if topic_text else ""
            lines.append(f"[daily_summary date={summary_date}{topic_suffix}] {summary[:900]}")
    for item in memories:
        if not _memory_matches_query(item, query_terms):
            continue
        kind = str(item.get("kind") or "memory")
        name = str(item.get("display_name") or item.get("username") or item.get("user_id") or "Unknown")
        summary = str(item.get("summary") or item.get("text") or "").replace("\n", " ").strip()
        reason = str(item.get("reason") or "").strip()
        if not summary or not is_memory_learning_safe(summary):
            continue
        prefix = f"[{kind} speaker={name[:80]}]"
        if reason:
            prefix = f"{prefix} reason={reason[:120]}"
        lines.append(f"{prefix} {summary[:500]}")
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
        if term and count > 0 and is_profile_context_value_safe(term):
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
        if text and is_profile_context_value_safe(text):
            samples.append(text[:220])
    return samples[-5:]


def _format_profile_list(value: Any, *, limit: int = 8) -> str:
    if not isinstance(value, list):
        return ""
    items = []
    for item in value:
        text = str(item or "").replace("\n", " ").strip()
        if text and is_profile_context_value_safe(text):
            items.append(text[:180])
        if len(items) >= limit:
            break
    return "; ".join(items)


def _format_profile_context(profiles: list[dict[str, Any]], *, intro: str) -> str:
    if not profiles:
        return ""

    lines = [intro]
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

        for field, label in (
            ("language_style", "observed_language_style"),
            ("interests", "self_observed_interests"),
            ("preferences", "self_stated_preferences"),
            ("known_facts", "self_stated_background"),
            ("boundaries", "self_stated_boundaries"),
        ):
            formatted = _format_profile_list(profile.get(field))
            if formatted:
                lines.append(f"  {label}: {formatted}")

        samples = _format_recent_samples(profile.get("recent_samples"))
        if samples:
            lines.append("  recent_own_messages:")
            for sample in samples:
                lines.append(f"  - {sample}")

    return "\n".join(lines)


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
    return _format_profile_context(
        profiles,
        intro="Trusted target-user profiles derived only from each user's own stored messages:",
    )


def format_requester_profile_context(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    *,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
) -> str:
    """Render trusted context about the user who asked the current question."""
    if requester_user_id is None:
        return ""

    profile = repo.get_user_profile(chat_id, requester_user_id)
    if not profile:
        profile = {
            "user_id": str(requester_user_id),
            "username": requester_username,
            "display_name": requester_display_name,
        }
    else:
        if requester_username and not profile.get("username"):
            profile = {**profile, "username": requester_username}
        if requester_display_name and not profile.get("display_name"):
            profile = {**profile, "display_name": requester_display_name}

    return _format_profile_context(
        [profile],
        intro="Trusted current requester profile derived only from the requester's own stored messages:",
    )
