"""Translate one authenticated Telegram message into the canonical source owner.

Quoted reply bodies and media analysis never enter this adapter. Invalidation is
performed before captcha/spam handling, including edits that cannot be learned.
"""

import re
from dataclasses import replace

from .ingestion import moderation_input_hash
from .models import MemoryInputError, MemorySourceConflict, MemoryUnavailable, SourceEvent
from .safety import require_public_content

_FACT_CONTROL_REF = re.compile(
    r"FACT#(?:USER#[1-9][0-9]{0,19}#(?:"
    r"(?:occupation|current_project|location)#current|"
    r"(?:education|tech_stack|interests)#[0-9a-f]{64}|"
    r"communication_preferences#(?:language|name|length|tone))|"
    r"GROUP#(?:rule|decision)#[0-9a-f]{64})@[1-9][0-9]{0,37}"
)


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
    words = text.split(maxsplit=3)
    command = words[0].split("@", 1)[0] if words else ""
    confirmation = command == "/memory" and (words[1:2] == ["correct"] or words[1:3] == ["group", "confirm"])
    if confirmation and words[1:2] == ["correct"] and len(words) >= 3 and _FACT_CONTROL_REF.fullmatch(words[2]):
        # A fact identity is control metadata, not a public claim (its Telegram ID
        # and hash can resemble phone numbers/secrets). Keep exact value/quote
        # offsets by replacing only this validated reference with equal-length
        # spaces before both OBS hashing and canonical confirmation RAW storage.
        token = list(re.finditer(r"\S+", text))[2]
        text = text[: token.start()] + " " * (token.end() - token.start()) + text[token.end() :]
    return SourceEvent(
        chat_id=message["chat"]["id"],
        message_id=str(message["message_id"]),
        actor_user_id=str(actor["id"]),
        original_sent_at=message["date"],
        edited_at=message.get("edit_date", 0),
        text=text,
        quoted_spans=quotes,
        source_kind="confirmation" if confirmation else "message",
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
            if update.get("edited_message") and getattr(ingestion, "repo", None) is not None:
                previous = ingestion.repo.get_observation(self.event.chat_id, self.event.message_id)
                if previous:
                    # The source lane is immutable. Classifying an edited command
                    # from its new text would reject observation before invalidation.
                    self.event = replace(self.event, source_kind=previous.get("source_kind", "message"))
            ingestion.observe(self.event)
            self.event.validate()
            require_public_content(self.event.text, max_length=20000)
            self.eligible = self.event.source_kind == "message" and not self.event.text.lstrip().startswith("/")
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
