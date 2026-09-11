"""Seven-day public topic frequencies, never personal interests or a fact writer.

Caller supplies a complete, current, source-valid snapshot and owns persistence,
daily scheduling, revalidation and invalidation after edits/optout/forget.
"""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from .extraction_prompt import validate_source
from .models import ExtractionSource, MemoryInputError, SourceRef, integer

WINDOW_SECONDS = 7 * 86400
MAX_TREND_SOURCES = 10000
# Versioned, explicit labels: these counts describe words discussed in the group.
# They cannot create a person's tech_stack/interests or a group rule/decision.
TOPIC_DICTIONARY_VERSION = "technical-topics-v1"
_TOPICS = {
    "python": ("python", "питон", "пайтон"),
    "javascript_typescript": ("javascript", "typescript", "nodejs", "node.js"),
    "databases": ("postgresql", "postgres", "mysql", "sqlite", "dynamodb", "sql", "база данных", "дерекқор"),
    "cloud_infrastructure": ("aws", "azure", "gcp", "kubernetes", "docker", "terraform"),
    "artificial_intelligence": ("llm", "gemini", "gpt", "machine learning", "нейросеть", "жасанды интеллект"),
    "software_delivery": ("git", "github", "gitlab", "ci/cd", "pytest", "тестирование", "тестілеу"),
    "web_development": ("react", "vue", "angular", "fastapi", "django", "веб", "frontend", "backend"),
    "mobile_development": ("android", "ios", "flutter", "swift", "kotlin"),
}
_PATTERNS = {
    topic: re.compile(r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)")
    for topic, terms in _TOPICS.items()
}


@dataclass(frozen=True)
class TopicTrend:
    topic: str
    message_count: int
    participant_count: int
    source_refs: tuple[SourceRef, ...]
    daily_message_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class TrendSnapshot:
    chat_id: str
    epoch: str
    as_of: int
    window_started_at: int
    eligible_source_count: int
    topics: tuple[TopicTrend, ...]
    dictionary_version: str = TOPIC_DICTIONARY_VERSION


def aggregate_trends(
    sources: list[ExtractionSource],
    *,
    chat_id: str,
    epoch: str,
    as_of: int,
) -> TrendSnapshot:
    from datetime import datetime, timezone

    integer(as_of, minimum=1)
    if len(sources) > MAX_TREND_SOURCES or not isinstance(epoch, str) or not epoch:
        raise MemoryInputError("Invalid trend snapshot boundary")
    messages, authors, days = defaultdict(list), defaultdict(set), defaultdict(lambda: defaultdict(int))
    eligible, seen = 0, set()
    for source in sources:
        validate_source(source)
        if str(source.chat_id) != str(chat_id) or source.ref.epoch != epoch:
            raise MemoryInputError("Trend snapshot mixes source scopes")
        if source.ref.source_id in seen:
            raise MemoryInputError("Trend snapshot contains duplicate source identities")
        seen.add(source.ref.source_id)
        if not as_of - WINDOW_SECONDS <= source.original_sent_at <= as_of:
            continue
        if source.edited_at > as_of:
            raise MemoryInputError("Trend snapshot contains a future edit")
        eligible += 1
        text = list(source.text)
        for start, end in source.quoted_spans:
            text[start:end] = " " * (end - start)
        folded = unicodedata.normalize("NFKC", "".join(text)).casefold()
        day = datetime.fromtimestamp(source.original_sent_at, timezone.utc).date().isoformat()
        for topic, pattern in _PATTERNS.items():
            if pattern.search(folded):
                messages[topic].append(source.ref)
                authors[topic].add(source.actor_user_id)
                days[topic][day] += 1
    trends = tuple(
        TopicTrend(
            topic,
            len(refs),
            len(authors[topic]),
            tuple(sorted(refs, key=lambda ref: (int(ref.source_id), ref.source_version))),
            tuple(sorted(days[topic].items())),
        )
        for topic, refs in sorted(messages.items(), key=lambda item: (-len(item[1]), item[0]))
    )
    return TrendSnapshot(str(chat_id), epoch, as_of, as_of - WINDOW_SECONDS, eligible, trends)
