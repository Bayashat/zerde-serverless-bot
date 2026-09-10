"""Small typed contracts shared by ingestion, extraction and fact reads."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass

from services.memory_safety import is_memory_learning_safe

RAW_RETENTION_SECONDS = 30 * 86400
HISTORY_RETENTION_SECONDS = 90 * 86400
FRESHNESS_SECONDS = 180 * 86400
WORK_RETENTION_SECONDS = 7 * 86400
WORK_INDEX_NAME = "work-due"
WORK_SHARDS = 4
CANDIDATE_RETENTION_SECONDS = 86400
WORK_LEASE_SECONDS = 130
SINGLE_FIELDS = {"occupation", "current_project", "location"}
MULTI_FIELDS = {"education", "tech_stack", "interests"}
PREFERENCE_FACETS = {"language", "name", "length", "tone"}
PERSONAL_FIELDS = SINGLE_FIELDS | MULTI_FIELDS | {"communication_preferences"}
GROUP_FIELDS = {"rule", "decision"}


class MemoryInputError(ValueError):
    """Invalid or unsupported domain input (never include raw input in errors)."""


class MemoryConflict(RuntimeError):
    """State changed since the caller's snapshot; read again before retrying."""


class MemoryUnavailable(RuntimeError):
    """Memory is stopped, opted out, stale, expired or pending deletion."""


def positive_id(value: str | int) -> str:
    if isinstance(value, bool) or len(str(value)) > 20 or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise MemoryInputError("Expected canonical positive Telegram identity")
    return str(value)


def chat_key(chat_id: str | int) -> str:
    if isinstance(chat_id, bool) or len(str(chat_id)) > 21 or not re.fullmatch(r"-?[1-9][0-9]*", str(chat_id)):
        raise MemoryInputError("Expected canonical Telegram chat identity")
    return f"CHAT#{chat_id}"


def integer(value, *, minimum=0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MemoryInputError("Expected nonnegative integer")
    return value


def normalise_value(value: str) -> str:
    if not isinstance(value, str):
        raise MemoryInputError("Fact value must be text")
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    if not value or len(value) > 160 or not is_memory_learning_safe(value):
        raise MemoryInputError("Unsupported fact value")
    return value


def work_queue(chat_id: str | int) -> str:
    shard = int(hashlib.sha256(str(chat_id).encode()).hexdigest(), 16) % WORK_SHARDS
    return f"MEMORY_WORK#{shard}"


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    source_version: int
    epoch: str

    def __post_init__(self):
        positive_id(self.source_id)
        if not isinstance(self.source_id, str):
            raise MemoryInputError("Source id must be string")
        integer(self.source_version, minimum=1)
        if not isinstance(self.epoch, str) or not self.epoch or len(self.epoch) > 64:
            raise MemoryInputError("Missing source epoch")

    def as_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class SourceEvent:
    chat_id: str | int
    message_id: str
    actor_user_id: str
    original_sent_at: int
    text: str
    edited_at: int = 0
    is_bot: bool = False
    is_forwarded: bool = False
    is_sender_chat: bool = False
    # Offset ranges in text; Telegram quoted/forwarded content is not a self claim.
    quoted_spans: tuple[tuple[int, int], ...] = ()
    source_kind: str = "message"

    def validate(self):
        self.validate_identity()
        if self.is_bot or self.is_forwarded or self.is_sender_chat:
            raise MemoryInputError("Only original personal messages are eligible")
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 20000:
            raise MemoryInputError("Invalid source text length")
        if not is_memory_learning_safe(self.text):
            raise MemoryInputError("Unsafe source text")
        for start, end in self.quoted_spans:
            integer(start)
            integer(end, minimum=1)
            if start >= end or end > len(self.text):
                raise MemoryInputError("Invalid quote offsets")

    def validate_identity(self):
        """Metadata invalidation must also accept an empty or unsafe edit body."""
        chat_key(self.chat_id)
        positive_id(self.message_id)
        positive_id(self.actor_user_id)
        integer(self.original_sent_at, minimum=1)
        integer(self.edited_at)
        if self.edited_at and self.edited_at < self.original_sent_at:
            raise MemoryInputError("Edit predates original source")
        if self.source_kind not in {"message", "confirmation"}:
            raise MemoryInputError("Unsupported source kind")
        if not isinstance(self.text, str):
            raise MemoryInputError("Source body must be text")


@dataclass(frozen=True)
class EvidenceSpan:
    start: int
    end: int

    def excerpt(self, raw: dict) -> str:
        integer(self.start)
        integer(self.end, minimum=1)
        text = raw["text"]
        if self.start >= self.end or self.end > len(text) or self.end - self.start > 240:
            raise MemoryInputError("Evidence must be a minimal exact source span")
        for start, end in raw.get("quoted_spans", []):
            if self.start < end and self.end > start:
                raise MemoryInputError("Quoted text cannot be self evidence")
        excerpt = text[self.start : self.end]
        if not excerpt.strip() or not is_memory_learning_safe(excerpt):
            raise MemoryInputError("Invalid evidence excerpt")
        return excerpt


@dataclass(frozen=True)
class FactChange:
    field: str
    value: str
    evidence: EvidenceSpan
    action: str = "assert"
    assertion_kind: str = "self_explicit"
    facet: str = ""
    valid_from: int | None = None

    def slot(self, *, group=False) -> tuple[str, str]:
        allowed = GROUP_FIELDS if group else PERSONAL_FIELDS
        if self.field not in allowed or self.action not in {"assert", "remove"}:
            raise MemoryInputError("Unsupported fact field or action")
        value = normalise_value(self.value)
        if self.field == "communication_preferences":
            if self.facet not in PREFERENCE_FACETS:
                raise MemoryInputError("Unsupported communication preference")
            allowed_values = {
                "length": {"short", "normal", "detailed"},
                "tone": {"formal", "friendly", "neutral"},
                "language": {"kk", "ru", "en", "zh"},
            }
            if self.facet in allowed_values and value.casefold() not in allowed_values[self.facet]:
                raise MemoryInputError("Unsupported preference value")
            return self.facet, value
        if self.facet:
            raise MemoryInputError("Unexpected fact facet")
        if self.field in SINGLE_FIELDS:
            return "current", value
        return hashlib.sha256(value.casefold().encode()).hexdigest(), value


@dataclass(frozen=True)
class WorkLease:
    source_ref: SourceRef
    token: str
    subject_generation: int
    lease_until: int

    def __post_init__(self):
        integer(self.subject_generation)
        integer(self.lease_until, minimum=1)
        if not isinstance(self.token, str) or not self.token:
            raise MemoryInputError("Missing work lease token")


@dataclass(frozen=True)
class AdminConfirmation:
    """Created only by a live Telegram authorization adapter, never model output."""

    actor_user_id: str
    confirmed: bool


@dataclass(frozen=True)
class CommitResult:
    source_ref: SourceRef
    written_fact_ids: tuple[str, ...]
    skipped: tuple[str, ...] = ()
    duplicate: bool = False


@dataclass(frozen=True)
class ExtractionSource:
    chat_id: str
    ref: SourceRef
    actor_user_id: str
    text: str
    quoted_spans: tuple[tuple[int, int], ...]
    original_sent_at: int
    edited_at: int = 0


@dataclass(frozen=True)
class ExtractionResult:
    ref: SourceRef
    changes: tuple[FactChange, ...] = ()
    status: str = "complete"
    reason: str = ""
    retry_at: int | None = None
