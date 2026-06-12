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

_TERM_RE = re.compile(r"[0-9a-zа-яәғқңөұүһіё][0-9a-zа-яәғқңөұүһіё+#._-]{1,}", flags=re.IGNORECASE)
_STOP_TERMS = {
    "about",
    "the",
    "and",
    "are",
    "bot",
    "chat",
    "for",
    "from",
    "with",
    "what",
    "who",
    "why",
    "how",
    "что",
    "как",
    "кто",
    "это",
    "про",
    "мен",
    "кім",
    "не",
    "осы",
    "сол",
}

_SOURCE_BASE_SCORES = {
    "requester_profile": 0.88,
    "target_profile": 0.84,
    "semantic": 0.16,
    "lexical": 0.14,
    "long_term": 0.08,
    "recent": 0.02,
}
_MEMORY_KIND_BASE_SCORES = {
    "profile": 0.0,
    "user_fact": 0.42,
    "group_fact": 0.36,
    "event": 0.34,
    "daily_summary": 0.24,
    "joke": 0.08,
    "memory": 0.22,
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


def extract_lexical_terms(text: str) -> set[str]:
    """Extract exact-match retrieval terms while keeping codes and short mixed terms."""
    terms: set[str] = set()
    for raw in _TERM_RE.findall(text or ""):
        term = raw.lower().lstrip("@#").strip("._-")
        if not term or term in _STOP_TERMS:
            continue
        if len(term) < 3 and not any(char.isdigit() for char in term):
            continue
        terms.add(term)
    return terms


def _query_terms(text: str) -> set[str]:
    return extract_lexical_terms(text)


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


def _item_memory_kind(item: dict[str, Any]) -> str | None:
    kind = str(item.get("kind") or "").strip()
    if kind:
        return kind
    sk = str(item.get("sk") or "")
    if sk.startswith("USER_FACT#"):
        return "user_fact"
    if sk.startswith("GROUP_FACT#"):
        return "group_fact"
    if sk.startswith("DAILY_SUMMARY#"):
        return "daily_summary"
    if sk.startswith("EVENT#"):
        return "event"
    if sk.startswith("JOKE#"):
        return "joke"
    return None


def _item_created_at(item: dict[str, Any]) -> int | None:
    try:
        return int(item.get("created_at")) if item.get("created_at") is not None else None
    except (TypeError, ValueError):
        return None


def _item_memory_text(item: dict[str, Any]) -> str:
    text = str(item.get("summary") or item.get("text") or "").replace("\n", " ").strip()
    return text


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _feedback_metadata_from_item(item: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    wrong_feedback_count = _int_value(item.get("wrong_feedback_count"))
    negative_feedback_count = _int_value(item.get("negative_feedback_count"))
    if wrong_feedback_count:
        metadata["wrong_feedback_count"] = wrong_feedback_count
    if negative_feedback_count:
        metadata["negative_feedback_count"] = negative_feedback_count
    if item.get("last_feedback_at") is not None:
        metadata["last_feedback_at"] = item.get("last_feedback_at")
    feedback_status = str(item.get("feedback_status") or "").strip()
    if feedback_status:
        metadata["feedback_status"] = feedback_status
    superseded_by = str(item.get("superseded_by") or "").strip()
    if superseded_by:
        metadata["superseded_by"] = superseded_by
    return metadata


def _lexical_candidate(item: dict[str, Any], query_terms: set[str]) -> MemoryCandidate | None:
    text = _item_memory_text(item)
    if not text or not is_memory_learning_safe(text):
        return None
    matched_terms = item.get("_lexical_terms")
    if not isinstance(matched_terms, list):
        matched_terms = sorted(term for term in query_terms if term in text.lower())
    memory_kind = _item_memory_kind(item)
    trust_level = {
        "user_fact": 58,
        "group_fact": 54,
        "event": 54,
        "daily_summary": 38,
        "joke": 24,
    }.get(memory_kind or "", 42)
    score = min(0.72, 0.34 + len(matched_terms) * 0.08)
    metadata = {
        "matched_terms": matched_terms[:12],
        "confidence": item.get("confidence"),
        "display_name": item.get("display_name"),
        "username": item.get("username"),
        **_feedback_metadata_from_item(item),
    }
    return MemoryCandidate(
        source="lexical",
        source_sk=str(item.get("sk") or "") or None,
        memory_kind=memory_kind,
        text=text,
        score=score,
        trust_level=trust_level,
        created_at=_item_created_at(item),
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _hydrate_candidate_feedback(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    candidate: MemoryCandidate,
) -> MemoryCandidate:
    if not candidate.source_sk:
        return candidate
    try:
        item = repo.get_memory_item(chat_id, candidate.source_sk)
    except Exception:
        return candidate
    if not isinstance(item, dict):
        return candidate
    feedback_metadata = _feedback_metadata_from_item(item)
    if not feedback_metadata:
        return candidate
    return replace(candidate, metadata={**candidate.metadata, **feedback_metadata})


def _format_lexical_memory_context(candidates: list[MemoryCandidate]) -> str:
    lines: list[str] = []
    for candidate in candidates:
        if candidate.source != "lexical" or not candidate.text or not is_memory_learning_safe(candidate.text):
            continue
        bits = [f"kind={candidate.memory_kind or 'memory'}"]
        if candidate.source_sk:
            bits.append(f"source={candidate.source_sk}")
        speaker = str(candidate.metadata.get("display_name") or candidate.metadata.get("username") or "").strip()
        if speaker:
            bits.append(f"speaker={speaker[:80]}")
        matched_terms = candidate.metadata.get("matched_terms")
        if isinstance(matched_terms, list) and matched_terms:
            bits.append("matches=" + ",".join(str(term) for term in matched_terms[:6]))
        lines.append(f"[lexical_memory {' '.join(bits)}] {candidate.text[:900]}")
    return "\n".join(lines)


def _format_semantic_candidate_context(candidate: MemoryCandidate) -> str:
    text = candidate.text.replace("\n", " ").strip()
    if not text or not is_memory_learning_safe(text):
        return ""
    bits = [f"kind={candidate.memory_kind or 'memory'}"]
    if candidate.source_sk:
        bits.append(f"source={candidate.source_sk}")
    speaker = str(
        candidate.metadata.get("display_name")
        or candidate.metadata.get("username")
        or candidate.metadata.get("user_id")
        or ""
    ).strip()
    if speaker:
        bits.append(f"speaker={speaker[:80]}")
    distance = candidate.metadata.get("distance")
    if isinstance(distance, int | float):
        bits.append(f"distance={distance:.4f}")
    return f"[semantic_memory {' '.join(bits)}] {text[:900]}"


def _render_candidate_context(candidate: MemoryCandidate) -> str:
    if candidate.source == "semantic":
        return _format_semantic_candidate_context(candidate)
    if candidate.source == "lexical":
        return _format_lexical_memory_context([candidate])
    text = candidate.text.strip()
    if not text:
        return ""
    return text


def _candidate_context_key(candidate: MemoryCandidate) -> str:
    if candidate.source == "requester_profile":
        return "requester_profile_context"
    if candidate.source == "target_profile":
        return "user_profile_context"
    if candidate.source == "semantic":
        return "semantic_memory_context"
    if candidate.source == "recent":
        return "recent_context"
    return "long_term_memory_context"


def _default_lexical_search(
    repo: GroupMemoryRepository,
    chat_id: int | str,
    terms: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    return repo.search_long_term_memories_by_terms(chat_id, terms, limit=limit)


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
    lexical_limit: int = 30,
    recent_context_fn: Callable[..., str] = format_recent_context,
    long_term_context_fn: Callable[..., str] = format_long_term_memory_context,
    semantic_retrieval_fn: Callable[..., list[dict[str, Any]]] = retrieve_relevant_memories,
    semantic_context_fn: Callable[[list[dict[str, Any]]], str] = format_semantic_memory_context,
    lexical_search_fn: Callable[[GroupMemoryRepository, int | str, set[str], int], list[dict[str, Any]]] = (
        _default_lexical_search
    ),
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
    semantic_candidates = [
        _hydrate_candidate_feedback(repo, chat_id, candidate)
        for row in semantic_rows
        if (candidate := _semantic_candidate(row)) is not None
    ]
    lexical_terms = extract_lexical_terms(user_text)
    lexical_rows = lexical_search_fn(repo, chat_id, lexical_terms, lexical_limit) if lexical_terms else []
    lexical_candidates = [
        candidate for row in lexical_rows if (candidate := _lexical_candidate(row, lexical_terms)) is not None
    ]
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
    candidates.extend(semantic_candidates)
    candidates.extend(lexical_candidates)
    candidates.extend(_context_line_candidates("long_term", long_term_context, trust_level=50))
    candidates.extend(_context_line_candidates("recent", recent_context, trust_level=20))
    return (
        {
            "recent_context": recent_context,
            "long_term_memory_context": long_term_context,
            "semantic_memory_context": "",
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
        score = _SOURCE_BASE_SCORES.get(candidate.source, 0.04)
        score += _MEMORY_KIND_BASE_SCORES.get(candidate.memory_kind or "memory", 0.22)
        if candidate.source in {"semantic", "lexical"}:
            score += max(0.0, min(1.0, candidate.score)) * (0.24 if candidate.source == "semantic" else 0.18)
        else:
            score += max(0.0, min(1.0, candidate.score)) * 0.08
        score += min(0.06, max(0, candidate.trust_level) / 1000.0)

        text_lower = candidate.text.lower()
        metadata_matches = candidate.metadata.get("matched_terms")
        exact_matches: set[str] = set()
        if isinstance(metadata_matches, list):
            exact_matches.update(str(term).lower() for term in metadata_matches if str(term).strip())
        exact_matches.update(term for term in terms if term in text_lower)
        score += min(0.18, len(exact_matches) * 0.045)

        if intent.target_usernames and any(username in text_lower for username in intent.target_usernames):
            score += 0.12
        if candidate.source == "requester_profile" and intent.is_self_reference:
            score += 0.08
        if candidate.source == "target_profile" and intent.target_usernames:
            score += 0.05
        if candidate.memory_kind in {"event", "daily_summary"} and (
            intent.asks_group_decision or intent.asks_past_event
        ):
            score += 0.12
        if candidate.memory_kind == "joke":
            score += 0.2 if intent.asks_joke_or_meme else -0.22
        if candidate.created_at:
            age_days = max(0.0, (now - candidate.created_at) / 86_400)
            score += max(-0.08, 0.06 - min(0.14, age_days / 365.0 * 0.14))
            if (
                candidate.memory_kind == "event"
                and age_days > 180
                and not (intent.asks_group_decision or intent.asks_past_event)
            ):
                score -= 0.08
            if candidate.memory_kind == "daily_summary" and age_days > 90 and not intent.asks_past_event:
                score -= 0.06
        if candidate.memory_kind == "daily_summary" and not (intent.asks_group_decision or intent.asks_past_event):
            score -= 0.06
        confidence = candidate.metadata.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence_value = None
        if confidence_value is not None:
            score += (confidence_value - 0.5) * 0.12
            if confidence_value < 0.4:
                score -= 0.06
        wrong_feedback_count = _int_value(candidate.metadata.get("wrong_feedback_count"))
        negative_feedback_count = _int_value(candidate.metadata.get("negative_feedback_count"))
        feedback_count = max(wrong_feedback_count, negative_feedback_count)
        if feedback_count:
            score -= min(0.36, 0.14 + feedback_count * 0.06)
        if str(candidate.metadata.get("feedback_status") or "").strip().lower() == "wrong":
            score -= 0.08
        if str(candidate.metadata.get("superseded_by") or "").strip():
            score -= 0.2

        scored.append(replace(candidate, score=max(0.0, min(1.0, score))))
    return sorted(scored, key=lambda item: (item.score, item.trust_level), reverse=True)


def dedupe_candidates(candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
    """Keep the highest-scoring candidate for duplicated source/text pairs."""
    deduped: dict[tuple[str, str], MemoryCandidate] = {}
    for candidate in candidates:
        normalized_text = " ".join(candidate.text.lower().split())[:500]
        key = ("source_sk", candidate.source_sk) if candidate.source_sk else (candidate.source, normalized_text)
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
    """Render and pack only selected reranked candidates into prompt sections."""
    remaining = max(0, int(char_budget))
    packed_lines: dict[str, list[str]] = {
        "requester_profile_context": [],
        "user_profile_context": [],
        "semantic_memory_context": [],
        "long_term_memory_context": [],
        "recent_context": [],
    }
    selected_candidates: list[MemoryCandidate] = []
    for candidate in candidates:
        if len(selected_candidates) >= source_limit:
            break
        key = _candidate_context_key(candidate)
        rendered = _render_candidate_context(candidate)
        if not rendered:
            continue
        separator_cost = 1 if packed_lines[key] else 0
        packed_text, remaining_after = _pack_text(rendered, remaining - separator_cost)
        if not packed_text:
            continue
        packed_lines[key].append(packed_text)
        remaining = remaining_after
        selected_candidates.append(candidate)

    selected_sources = [candidate.source_metadata() for candidate in selected_candidates]
    return RetrievalBundle(
        intent=intent,
        recent_context="\n".join(packed_lines["recent_context"]),
        long_term_memory_context="\n".join(packed_lines["long_term_memory_context"]),
        semantic_memory_context="\n".join(packed_lines["semantic_memory_context"]),
        user_profile_context="\n".join(packed_lines["user_profile_context"]),
        requester_profile_context="\n".join(packed_lines["requester_profile_context"]),
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
    lexical_limit: int = 30,
    char_budget: int = 12_000,
    recent_context_fn: Callable[..., str] = format_recent_context,
    long_term_context_fn: Callable[..., str] = format_long_term_memory_context,
    semantic_retrieval_fn: Callable[..., list[dict[str, Any]]] = retrieve_relevant_memories,
    semantic_context_fn: Callable[[list[dict[str, Any]]], str] = format_semantic_memory_context,
    lexical_search_fn: Callable[[GroupMemoryRepository, int | str, set[str], int], list[dict[str, Any]]] = (
        _default_lexical_search
    ),
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
        lexical_limit=lexical_limit,
        recent_context_fn=recent_context_fn,
        long_term_context_fn=long_term_context_fn,
        semantic_retrieval_fn=semantic_retrieval_fn,
        semantic_context_fn=semantic_context_fn,
        lexical_search_fn=lexical_search_fn,
        user_profile_context_fn=user_profile_context_fn,
        requester_profile_context_fn=requester_profile_context_fn,
    )
    scored = dedupe_candidates(score_candidates(candidates, intent=intent, user_text=user_text))
    return pack_context(intent=intent, contexts=contexts, candidates=scored, char_budget=char_budget)
