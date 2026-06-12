"""Import Telegram Desktop JSON exports into group memory."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

from services.memory_extractor import MemoryClassification, classify_long_term_memory_rule_based
from services.repositories.group_memory import GroupMemoryRepository
from services.vector_memory import looks_sensitive_for_embedding

VectorEnqueue = Callable[..., None]

_WORD_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{2,}", re.IGNORECASE)
_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "that",
    "the",
    "this",
    "with",
    "you",
    "your",
    "мен",
    "сен",
    "сол",
    "бұл",
    "бір",
    "үшін",
    "деп",
    "ғой",
    "бар",
    "жоқ",
    "как",
    "что",
    "это",
    "для",
    "или",
    "она",
    "они",
    "есть",
    "нет",
}


@dataclass(frozen=True)
class TelegramExportMessage:
    message_id: int
    created_at: int
    display_name: str
    user_id: str
    username: str | None
    text: str

    @property
    def summary_date(self) -> str:
        return datetime.fromtimestamp(self.created_at, UTC).date().isoformat()


@dataclass
class HistoryImportStats:
    total_export_messages: int = 0
    parsed_messages: int = 0
    skipped_outside_range: int = 0
    skipped_empty: int = 0
    skipped_service: int = 0
    skipped_command: int = 0
    skipped_sensitive: int = 0
    duplicate_messages: int = 0
    stored_messages: int = 0
    long_term_memories: int = 0
    daily_summaries: int = 0
    vector_tasks: int = 0
    long_term_by_kind: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_export_messages": self.total_export_messages,
            "parsed_messages": self.parsed_messages,
            "skipped_outside_range": self.skipped_outside_range,
            "skipped_empty": self.skipped_empty,
            "skipped_service": self.skipped_service,
            "skipped_command": self.skipped_command,
            "skipped_sensitive": self.skipped_sensitive,
            "duplicate_messages": self.duplicate_messages,
            "stored_messages": self.stored_messages,
            "long_term_memories": self.long_term_memories,
            "daily_summaries": self.daily_summaries,
            "vector_tasks": self.vector_tasks,
            "long_term_by_kind": dict(self.long_term_by_kind),
        }


@dataclass(frozen=True)
class HistoryImportOptions:
    chat_id: int | str
    export_path: Path
    since: date
    until: date | None = None
    dry_run: bool = True
    store_raw_messages: bool = True
    extract_long_term: bool = True
    create_daily_summaries: bool = True
    enqueue_vectors: bool = True
    vectorize_daily_summaries: bool = False
    max_messages: int | None = None


@dataclass
class HistoryImportResult:
    stats: HistoryImportStats
    date_range: tuple[str | None, str | None]
    daily_message_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "stats": self.stats.as_dict(),
            "date_range": {"first": self.date_range[0], "last": self.date_range[1]},
            "daily_message_counts": self.daily_message_counts,
        }


def load_telegram_export(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError("Telegram export JSON must be an object")
    if not isinstance(data.get("messages"), list):
        raise ValueError("Telegram export JSON must contain a messages list")
    return data


def text_from_telegram_export(value: Any) -> str:
    """Flatten Telegram Desktop's string/list rich-text export shape."""
    if isinstance(value, str):
        return " ".join(value.split())
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text") or ""))
    return " ".join("".join(parts).split())


def parse_export_timestamp(row: dict[str, Any]) -> int | None:
    raw_unixtime = row.get("date_unixtime")
    if raw_unixtime not in (None, ""):
        try:
            return int(raw_unixtime)
        except (TypeError, ValueError):
            pass

    raw_date = row.get("date")
    if not raw_date:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return int(parsed.timestamp())


def normalise_export_user_id(row: dict[str, Any]) -> str:
    raw = row.get("from_id") or row.get("actor_id") or row.get("sender_id")
    if raw:
        value = str(raw)
        for prefix in ("user", "channel", "chat"):
            if value.startswith(prefix):
                value = value.removeprefix(prefix)
        return value or "unknown"
    name = str(row.get("from") or row.get("actor") or "unknown").strip().lower()
    return f"export:{sha256(name.encode('utf-8')).hexdigest()[:16]}"


def parse_telegram_export_messages(
    data: dict[str, Any],
    *,
    since: date,
    until: date | None = None,
    stats: HistoryImportStats | None = None,
) -> list[TelegramExportMessage]:
    stats = stats or HistoryImportStats()
    rows = data.get("messages") if isinstance(data.get("messages"), list) else []
    stats.total_export_messages = len(rows)
    messages: list[TelegramExportMessage] = []
    start_epoch = int(datetime.combine(since, time.min, tzinfo=UTC).timestamp())
    end_epoch = None
    if until is not None:
        end_epoch = int(datetime.combine(until, time.max, tzinfo=UTC).timestamp())

    for row in rows:
        if not isinstance(row, dict):
            stats.skipped_service += 1
            continue
        if row.get("type") not in (None, "message"):
            stats.skipped_service += 1
            continue
        message_id = row.get("id")
        created_at = parse_export_timestamp(row)
        if not isinstance(message_id, int) or created_at is None:
            stats.skipped_service += 1
            continue
        if created_at < start_epoch or (end_epoch is not None and created_at > end_epoch):
            stats.skipped_outside_range += 1
            continue
        text = text_from_telegram_export(row.get("text"))
        if not text:
            text = text_from_telegram_export(row.get("caption"))
        if not text:
            stats.skipped_empty += 1
            continue
        if text.startswith("/"):
            stats.skipped_command += 1
            continue
        if looks_sensitive_for_embedding(text):
            stats.skipped_sensitive += 1
            continue
        display_name = str(row.get("from") or row.get("actor") or row.get("author") or "Unknown").strip()
        messages.append(
            TelegramExportMessage(
                message_id=message_id,
                created_at=created_at,
                display_name=display_name[:80] or "Unknown",
                user_id=normalise_export_user_id(row),
                username=None,
                text=text[:4000],
            )
        )
    messages.sort(key=lambda item: (item.created_at, item.message_id))
    stats.parsed_messages = len(messages)
    return messages


def _terms_for_text(text: str) -> list[str]:
    cleaned = re.sub(r"https?://\S+|@\w+|/\w+", " ", text.lower())
    terms: list[str] = []
    seen: set[str] = set()
    for match in _WORD_RE.finditer(cleaned):
        term = match.group(0)
        if term in _STOPWORDS or term.isdigit() or term in seen:
            continue
        seen.add(term)
        terms.append(term[:40])
        if len(terms) >= 20:
            break
    return terms


def _top_terms(messages: Iterable[TelegramExportMessage], *, limit: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    for message in messages:
        counts.update(_terms_for_text(message.text))
    return [term for term, _ in counts.most_common(limit)]


def build_history_daily_summary(
    summary_date: str,
    messages: list[TelegramExportMessage],
    classifications: list[tuple[TelegramExportMessage, MemoryClassification]],
) -> dict[str, Any]:
    participant_counts = Counter(message.display_name for message in messages)
    active_participants = [name for name, _ in participant_counts.most_common(20)]
    topics = _top_terms(messages)
    notable_events = [
        classification.summary
        for _, classification in classifications
        if classification.kind in {"event", "group_fact"}
    ][:12]
    inside_jokes = [classification.summary for _, classification in classifications if classification.kind == "joke"][
        :8
    ]
    summary_parts = [
        f"{summary_date}: imported {len(messages)} Telegram export messages",
        f"from {len(participant_counts)} participants",
    ]
    if topics:
        summary_parts.append(f"frequent topics: {', '.join(topics[:8])}")
    if notable_events:
        summary_parts.append(f"notable memory signals: {'; '.join(notable_events[:3])}")
    return {
        "summary": ". ".join(summary_parts)[:1200],
        "topics": topics,
        "notable_events": notable_events,
        "inside_jokes": inside_jokes,
        "active_participants": active_participants,
        "tension_points": [],
        "source": "telegram_export_import",
    }


def import_telegram_history(
    options: HistoryImportOptions,
    *,
    repo: GroupMemoryRepository | None = None,
    vector_enqueue: VectorEnqueue | None = None,
) -> HistoryImportResult:
    """Import one Telegram Desktop JSON export into group memory."""
    stats = HistoryImportStats()
    data = load_telegram_export(options.export_path)
    messages = parse_telegram_export_messages(data, since=options.since, until=options.until, stats=stats)
    if options.max_messages is not None:
        messages = messages[: max(0, options.max_messages)]
        stats.parsed_messages = len(messages)

    repo = repo or (None if options.dry_run else GroupMemoryRepository())
    by_day: dict[str, list[TelegramExportMessage]] = defaultdict(list)
    classifications_by_day: dict[str, list[tuple[TelegramExportMessage, MemoryClassification]]] = defaultdict(list)

    for message in messages:
        by_day[message.summary_date].append(message)
        if repo is not None and not options.dry_run and options.store_raw_messages:
            stored = repo.store_message(
                chat_id=options.chat_id,
                message_id=message.message_id,
                user_id=message.user_id,
                display_name=message.display_name,
                username=message.username,
                text=message.text,
                created_at=message.created_at,
                skip_if_exists=True,
            )
            if stored:
                stats.stored_messages += 1
            else:
                stats.duplicate_messages += 1

        classification = classify_long_term_memory_rule_based(message.text) if options.extract_long_term else None
        if not classification:
            continue
        classifications_by_day[message.summary_date].append((message, classification))
        stats.long_term_memories += 1
        stats.long_term_by_kind[classification.kind] += 1
        if repo is None or options.dry_run:
            continue
        item = repo.store_long_term_memory(
            chat_id=options.chat_id,
            message_id=message.message_id,
            user_id=message.user_id,
            display_name=message.display_name,
            username=message.username,
            text=message.text,
            kind=classification.kind,
            summary=classification.summary,
            reason=f"telegram export import: {classification.reason}",
            confidence=classification.confidence,
            created_at=message.created_at,
        )
        _enqueue_vector(options, vector_enqueue, item["sk"], stats)

    if options.create_daily_summaries:
        for summary_date in sorted(by_day):
            daily = build_history_daily_summary(
                summary_date,
                by_day[summary_date],
                classifications_by_day.get(summary_date, []),
            )
            stats.daily_summaries += 1
            if repo is None or options.dry_run:
                continue
            item = repo.store_daily_summary(
                chat_id=options.chat_id,
                summary_date=summary_date,
                summary=daily["summary"],
                topics=daily["topics"],
                notable_events=daily["notable_events"],
                inside_jokes=daily["inside_jokes"],
                active_participants=daily["active_participants"],
                tension_points=daily["tension_points"],
                message_count=len(by_day[summary_date]),
                source=daily["source"],
            )
            if options.vectorize_daily_summaries:
                _enqueue_vector(options, vector_enqueue, item["sk"], stats)

    first_day = min(by_day) if by_day else None
    last_day = max(by_day) if by_day else None
    return HistoryImportResult(
        stats=stats,
        date_range=(first_day, last_day),
        daily_message_counts={day: len(items) for day, items in sorted(by_day.items())},
    )


def _enqueue_vector(
    options: HistoryImportOptions,
    vector_enqueue: VectorEnqueue | None,
    source_sk: str,
    stats: HistoryImportStats,
) -> None:
    if not options.enqueue_vectors or vector_enqueue is None:
        return
    vector_enqueue(chat_id=options.chat_id, source_sk=source_sk, reason="telegram_history_import")
    stats.vector_tasks += 1
