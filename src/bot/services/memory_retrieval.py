"""Thin retrieval pipeline wrapper for group-agent memory context."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from services.group_memory import (
    extract_mentioned_usernames,
    format_long_term_memory_context,
    format_recent_context,
    format_requester_profile_context,
    format_user_profile_context,
)
from services.memory_safety import is_memory_learning_safe
from services.repositories.group_memory import GroupMemoryRepository
from services.vector_memory import format_semantic_memory_context, retrieve_relevant_memories

_SELF_REFERENCE_CUES = (
    "who am i",
    "what do you know about me",
    "what did i say",
    "did i say",
    "我是谁",
    "你知道我",
    "我说过",
    "кто я",
    "я кто",
    "что ты знаешь обо мне",
    "что я говорил",
    "что я сказал",
    "мен кім",
    "мен кіммін",
    "мен не дедім",
)

_GROUP_DECISION_CUES = (
    "decide",
    "decided",
    "choose",
    "chose",
    "picked",
    "agreed",
    "what did we pick",
    "решили",
    "выбрали",
    "договорились",
    "таңдадық",
    "шештік",
    "келістік",
    "决定",
    "选择",
)

_PAST_EVENT_CUES = (
    "what happened",
    "when did",
    "yesterday",
    "last week",
    "last month",
    "раньше",
    "вчера",
    "когда",
    "что было",
    "не болды",
    "қашан",
    "кеше",
    "以前",
    "昨天",
    "发生",
)

_JOKE_CUES = (
    "joke",
    "meme",
    "inside joke",
    "шутк",
    "мем",
    "прикол",
    "әзіл",
    "қалжың",
    "мем",
    "笑话",
    "梗",
)

_TIME_HINT_RE = re.compile(
    r"\b(?:today|yesterday|tomorrow|last\s+\w+|next\s+\w+|"
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\b",
    flags=re.IGNORECASE,
)

_TERM_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё+#._-]{3,}", flags=re.IGNORECASE)
_STOP_TERMS = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "who",
    "why",
    "how",
    "что",
    "как",
    "кто",
    "это",
    "мен",
    "кім",
    "не",
}


@dataclass(frozen=True)
class RetrievalIntent:
    is_self_reference: bool
    target_usernames: set[str]
    target_user_ids: set[str]
    asks_group_decision: bool
    asks_past_event: bool
    asks_joke_or_meme: bool
    time_hint: str | None


@dataclass(frozen=True)
class MemoryCandidate:
    source: str
    source_sk: str | None
    memory_kind: str | None
    text: str
    score: float
    trust_level: int
    created_at: int | None
    metadata: dict[str, Any]

    def source_metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "source": self.source,
            "score": round(max(0.0, min(1.0, self.score)), 4),
            "trust_level": self.trust_level,
        }
        if self.source_sk:
            data["source_sk"] = self.source_sk
        if self.memory_kind:
            data["memory_kind"] = self.memory_kind
        if self.created_at is not None:
            data["created_at"] = self.created_at
        return data


@dataclass(frozen=True)
class RetrievalBundle:
    intent: RetrievalIntent
    recent_context: str
    long_term_memory_context: str
    semantic_memory_context: str
    user_profile_context: str
    requester_profile_context: str
    candidates: list[MemoryCandidate]
    retrieval_sources: list[dict[str, Any]]


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    lowered = " ".join((text or "").lower().split())
    compact = lowered.replace(" ", "")
    return any(cue in lowered or cue.replace(" ", "") in compact for cue in cues)


def analyze_query_intent(
    user_text: str,
    requester_user_id: int | str | None = None,
    *,
    ignored_usernames: set[str] | None = None,
) -> RetrievalIntent:
    """Extract a small, local intent signal set for retrieval decisions."""
    ignored = {item.lower().lstrip("@") for item in (ignored_usernames or set()) if item}
    target_usernames = extract_mentioned_usernames(user_text, ignore=ignored)
    target_user_ids = (
        {str(requester_user_id)}
        if requester_user_id is not None and _contains_any(user_text, _SELF_REFERENCE_CUES)
        else set()
    )
    time_match = _TIME_HINT_RE.search(user_text or "")
    return RetrievalIntent(
        is_self_reference=_contains_any(user_text, _SELF_REFERENCE_CUES),
        target_usernames=target_usernames,
        target_user_ids=target_user_ids,
        asks_group_decision=_contains_any(user_text, _GROUP_DECISION_CUES),
        asks_past_event=_contains_any(user_text, _PAST_EVENT_CUES),
        asks_joke_or_meme=_contains_any(user_text, _JOKE_CUES),
        time_hint=time_match.group(0) if time_match else None,
    )


def _query_terms(text: str) -> set[str]:
    return {term.lower().lstrip("@") for term in _TERM_RE.findall(text or "") if term.lower() not in _STOP_TERMS}


def _line_kind(line: str) -> str | None:
    match = re.match(r"\[([a-z_]+)", line.strip())
    return match.group(1) if match else None


def _semantic_candidate(row: dict[str, Any]) -> MemoryCandidate | None:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    text = str(metadata.get("text") or "").replace("\n", " ").strip()
    if not text or not is_memory_learning_safe(text):
        return None
    distance = row.get("distance")
    similarity_score = 0.5
    if isinstance(distance, int | float):
        similarity_score = max(0.0, min(1.0, 1.0 - float(distance)))
    created_at = metadata.get("created_at")
    try:
        created_at_int = int(created_at) if created_at is not None else None
    except (TypeError, ValueError):
        created_at_int = None
    return MemoryCandidate(
        source="semantic",
        source_sk=str(metadata.get("source_sk") or "") or None,
        memory_kind=str(metadata.get("memory_kind") or "") or None,
        text=text,
        score=similarity_score,
        trust_level=60,
        created_at=created_at_int,
        metadata={**metadata, "distance": distance},
    )


def _context_line_candidates(source: str, context: str, *, trust_level: int) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    for line in context.splitlines():
        text = line.strip()
        if not text:
            continue
        candidates.append(
            MemoryCandidate(
                source=source,
                source_sk=None,
                memory_kind=_line_kind(text),
                text=text,
                score=0.0,
                trust_level=trust_level,
                created_at=None,
                metadata={},
            )
        )
    return candidates


def retrieve_candidates(
    *,
    repo: GroupMemoryRepository,
    chat_id: int | str,
    user_text: str,
    intent: RetrievalIntent,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
    ignored_usernames: set[str] | None = None,
    recent_limit: int | None = None,
    semantic_limit: int = 8,
    recent_context_fn: Callable[..., str] = format_recent_context,
    long_term_context_fn: Callable[..., str] = format_long_term_memory_context,
    semantic_retrieval_fn: Callable[..., list[dict[str, Any]]] = retrieve_relevant_memories,
    semantic_context_fn: Callable[[list[dict[str, Any]]], str] = format_semantic_memory_context,
    user_profile_context_fn: Callable[..., str] = format_user_profile_context,
    requester_profile_context_fn: Callable[..., str] = format_requester_profile_context,
) -> tuple[dict[str, str], list[MemoryCandidate]]:
    """Call existing retrievers/formatters and convert their output to candidates."""
    recent_context = recent_context_fn(repo, chat_id, limit=recent_limit)
    long_term_context = long_term_context_fn(repo, chat_id, query_text=user_text)
    semantic_rows = semantic_retrieval_fn(
        chat_id,
        user_text,
        limit=semantic_limit,
        user_id=requester_user_id if intent.is_self_reference else None,
    )
    semantic_context = semantic_context_fn(semantic_rows)
    user_profile_context = user_profile_context_fn(
        repo,
        chat_id,
        user_text=user_text,
        ignored_usernames=ignored_usernames,
    )
    requester_profile_context = requester_profile_context_fn(
        repo,
        chat_id,
        requester_user_id=requester_user_id,
        requester_username=requester_username,
        requester_display_name=requester_display_name,
    )

    candidates: list[MemoryCandidate] = []
    if requester_profile_context:
        candidates.append(
            MemoryCandidate(
                source="requester_profile",
                source_sk=f"USER#{requester_user_id}" if requester_user_id is not None else None,
                memory_kind="profile",
                text=requester_profile_context,
                score=0.0,
                trust_level=100,
                created_at=None,
                metadata={"requester_user_id": str(requester_user_id) if requester_user_id is not None else ""},
            )
        )
    if user_profile_context:
        candidates.append(
            MemoryCandidate(
                source="target_profile",
                source_sk=None,
                memory_kind="profile",
                text=user_profile_context,
                score=0.0,
                trust_level=90,
                created_at=None,
                metadata={"target_usernames": sorted(intent.target_usernames)},
            )
        )
    for row in semantic_rows:
        candidate = _semantic_candidate(row)
        if candidate:
            candidates.append(candidate)
    candidates.extend(_context_line_candidates("long_term", long_term_context, trust_level=50))
    candidates.extend(_context_line_candidates("recent", recent_context, trust_level=20))
    return (
        {
            "recent_context": recent_context,
            "long_term_memory_context": long_term_context,
            "semantic_memory_context": semantic_context,
            "user_profile_context": user_profile_context,
            "requester_profile_context": requester_profile_context,
        },
        candidates,
    )


def score_candidates(
    candidates: list[MemoryCandidate],
    *,
    intent: RetrievalIntent,
    user_text: str,
    now: int | None = None,
) -> list[MemoryCandidate]:
    """Apply explainable local scores without changing the underlying retrievers."""
    now = int(time.time()) if now is None else now
    terms = _query_terms(user_text)
    scored: list[MemoryCandidate] = []
    for candidate in candidates:
        score = candidate.score + candidate.trust_level / 120.0
        text_lower = candidate.text.lower()
        exact_matches = sum(1 for term in terms if term in text_lower)
        score += min(0.2, exact_matches * 0.04)

        if intent.target_usernames and any(username in text_lower for username in intent.target_usernames):
            score += 0.2
        if candidate.source == "requester_profile" and intent.is_self_reference:
            score += 0.25
        if candidate.memory_kind in {"event", "daily_summary"} and (
            intent.asks_group_decision or intent.asks_past_event
        ):
            score += 0.12
        if candidate.memory_kind == "joke":
            score += 0.2 if intent.asks_joke_or_meme else -0.25
        if candidate.created_at:
            age_days = max(0.0, (now - candidate.created_at) / 86_400)
            score += max(-0.1, 0.08 - min(0.18, age_days / 365.0 * 0.18))
        confidence = candidate.metadata.get("confidence")
        if isinstance(confidence, int | float):
            score += (float(confidence) - 0.5) * 0.16

        scored.append(replace(candidate, score=max(0.0, min(1.0, score))))
    return sorted(scored, key=lambda item: (item.score, item.trust_level), reverse=True)


def dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    """Keep the highest-scoring candidate for duplicated source/text pairs."""
    deduped: dict[tuple[str | None, str], MemoryCandidate] = {}
    for candidate in candidates:
        normalized_text = " ".join(candidate.text.lower().split())[:500]
        key = (candidate.source_sk, normalized_text)
        existing = deduped.get(key)
        if existing is None or (candidate.score, candidate.trust_level) > (existing.score, existing.trust_level):
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda item: (item.score, item.trust_level), reverse=True)


def _pack_text(text: str, remaining: int) -> tuple[str, int]:
    if remaining <= 0 or not text:
        return "", remaining
    packed_lines: list[str] = []
    used = 0
    for line in text.splitlines():
        candidate = line if not packed_lines else "\n" + line
        candidate_len = len(candidate)
        if used + candidate_len > remaining:
            break
        packed_lines.append(line)
        used += candidate_len
    return "\n".join(packed_lines), remaining - used


def pack_context(
    *,
    intent: RetrievalIntent,
    contexts: dict[str, str],
    candidates: list[MemoryCandidate],
    char_budget: int = 12_000,
    source_limit: int = 16,
) -> RetrievalBundle:
    """Pack context sections in trust order and return source metadata."""
    remaining = max(0, int(char_budget))
    packed: dict[str, str] = {}
    for key in (
        "requester_profile_context",
        "user_profile_context",
        "semantic_memory_context",
        "long_term_memory_context",
        "recent_context",
    ):
        packed[key], remaining = _pack_text(contexts.get(key, ""), remaining)

    selected_sources = [candidate.source_metadata() for candidate in candidates[:source_limit]]
    return RetrievalBundle(
        intent=intent,
        recent_context=packed["recent_context"],
        long_term_memory_context=packed["long_term_memory_context"],
        semantic_memory_context=packed["semantic_memory_context"],
        user_profile_context=packed["user_profile_context"],
        requester_profile_context=packed["requester_profile_context"],
        candidates=candidates,
        retrieval_sources=selected_sources,
    )


def build_agent_memory_context(
    *,
    repo: GroupMemoryRepository,
    chat_id: int | str,
    user_text: str,
    requester_user_id: int | str | None = None,
    requester_username: str | None = None,
    requester_display_name: str | None = None,
    ignored_usernames: set[str] | None = None,
    recent_limit: int | None = None,
    semantic_limit: int = 8,
    char_budget: int = 12_000,
    recent_context_fn: Callable[..., str] = format_recent_context,
    long_term_context_fn: Callable[..., str] = format_long_term_memory_context,
    semantic_retrieval_fn: Callable[..., list[dict[str, Any]]] = retrieve_relevant_memories,
    semantic_context_fn: Callable[[list[dict[str, Any]]], str] = format_semantic_memory_context,
    user_profile_context_fn: Callable[..., str] = format_user_profile_context,
    requester_profile_context_fn: Callable[..., str] = format_requester_profile_context,
) -> RetrievalBundle:
    """Build agent prompt contexts plus retrieval source metadata."""
    intent = analyze_query_intent(user_text, requester_user_id, ignored_usernames=ignored_usernames)
    contexts, candidates = retrieve_candidates(
        repo=repo,
        chat_id=chat_id,
        user_text=user_text,
        intent=intent,
        requester_user_id=requester_user_id,
        requester_username=requester_username,
        requester_display_name=requester_display_name,
        ignored_usernames=ignored_usernames,
        recent_limit=recent_limit,
        semantic_limit=semantic_limit,
        recent_context_fn=recent_context_fn,
        long_term_context_fn=long_term_context_fn,
        semantic_retrieval_fn=semantic_retrieval_fn,
        semantic_context_fn=semantic_context_fn,
        user_profile_context_fn=user_profile_context_fn,
        requester_profile_context_fn=requester_profile_context_fn,
    )
    scored = dedupe_candidates(score_candidates(candidates, intent=intent, user_text=user_text))
    return pack_context(intent=intent, contexts=contexts, candidates=scored, char_budget=char_budget)
