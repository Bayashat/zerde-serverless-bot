"""Translate one authenticated Telegram message into the canonical source owner.

Quoted reply bodies and media analysis never enter this adapter. Invalidation is
performed before captcha/spam handling, including edits that cannot be learned.
"""

from .ingestion import moderation_input_hash
from .models import MemoryInputError, MemorySourceConflict, MemoryUnavailable, SourceEvent
from .safety import require_public_content


def _quote_spans(text, entities):
    # Telegram offsets count UTF-16 code units; model evidence uses Python indices.
    boundaries, units = {0: 0}, 0
    for index, char in enumerate(text):
        units += len(char.encode("utf-16-le")) // 2
        boundaries[units] = index + 1
    spans = []
    for entity in entities:
        if entity.get("type") not in {"blockquote", "expandable_blockquote"}:
            continue
        offset, length = entity.get("offset"), entity.get("length")
        if type(offset) is not int or type(length) is not int or length <= 0:
            raise MemoryInputError("Invalid Telegram quote range")
        if offset not in boundaries or offset + length not in boundaries:
            raise MemoryInputError("Invalid Telegram UTF-16 boundary")
        spans.append((boundaries[offset], boundaries[offset + length]))
    return tuple(sorted(spans))


def source_event(update):
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict) or message.get("chat", {}).get("type") not in {"group", "supergroup"}:
        return None
    actor = message.get("from") or {}
    if not actor.get("id") or actor.get("is_bot") or message.get("sender_chat"):
        return None
    text = message.get("text", message.get("caption", ""))
    if not isinstance(text, str):
        raise MemoryInputError("Invalid Telegram source text")
    entities = message.get("entities" if "text" in message else "caption_entities") or []
    try:
        quotes = _quote_spans(text, entities)
    except (MemoryInputError, AttributeError, TypeError):
        # Still invalidate a previous source; an unparseable quote cannot become self evidence.
        quotes = ((0, len(text)),) if text else ()
    return SourceEvent(
        chat_id=message["chat"]["id"],
        message_id=str(message["message_id"]),
        actor_user_id=str(actor["id"]),
        original_sent_at=message["date"],
        edited_at=message.get("edit_date", 0),
        text=text,
        quoted_spans=quotes,
        is_forwarded=any(
            message.get(key)
            for key in ("forward_origin", "forward_date", "forward_from", "forward_from_chat", "is_automatic_forward")
        ),
    )


class TelegramMemoryAdmission:
    """One update; expected ineligible sources are distinct from retryable DB errors."""

    def __init__(self, ingestion, update):
        self.ingestion = ingestion
        self.event = None
        self.eligible = False
        if ingestion is None:
            return
        try:
            self.event = source_event(update)
            if self.event is None:
                return
            ingestion.observe(self.event)
            self.event.validate()
            require_public_content(self.event.text, max_length=20000)
            self.eligible = not self.event.text.lstrip().startswith("/")
        except (MemoryUnavailable, MemoryInputError, MemorySourceConflict):
            self.eligible = False

    def prepare(self, text, message_context):
        if not self.eligible:
            return None
        try:
            ref = self.ingestion.prepare(self.event, moderation_input_hash(text, message_context))
        except (MemoryUnavailable, MemoryInputError, MemorySourceConflict):
            return None
        return ref.as_dict()

    def accept_safe(self):
        if not self.eligible:
            return
        try:
            self.ingestion.accept_safe(self.event)
        except (MemoryUnavailable, MemoryInputError, MemorySourceConflict):
            return
