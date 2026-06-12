"""Semantic retrieval over trusted long-term group memory."""

from __future__ import annotations

import hashlib
import json
import re
import time
from decimal import Decimal
from typing import Any

import urllib3
from core.config import (
    GEMINI_API_BASE,
    VECTOR_MEMORY_BACKFILL_BATCH_SIZE,
    VECTOR_MEMORY_DIMENSIONS,
    VECTOR_MEMORY_EMBEDDING_MODEL,
    VECTOR_MEMORY_ENABLED,
    VECTOR_MEMORY_INDEX_THROTTLE_SECONDS,
    VECTOR_MEMORY_MAX_DISTANCE,
    VECTOR_MEMORY_PROVIDER,
    get_gemini_embedding_api_key,
)
from core.logger import LoggerAdapter, get_logger
from services.memory_safety import is_memory_learning_safe
from services.repositories.group_memory import GroupMemoryRepository
from services.repositories.vector_memory import S3VectorMemoryRepository
from urllib3.exceptions import HTTPError

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(connect=2, read=10))
_embedding_client: "GeminiEmbeddingClient | None" = None

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<![\w+])(?:\+\d[\d\s().-]{7,}\d|\d{10,15})(?!\w)")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?:api[_ -]?key|token|secret|password|passwd|bearer|authorization)\s*[:=]",
    flags=re.IGNORECASE,
)
_LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_-]{36,}\b")
_SECRET_CUES = (
    "password",
    "passwd",
    "secret",
    "api key",
    "token",
    "bearer",
    "authorization",
    "пароль",
    "құпия",
    "密码",
    "令牌",
)
_SENSITIVE_CUES = (
    "diagnosis",
    "medical",
    "salary",
    "passport",
    "credit card",
    "диагноз",
    "зарплата",
    "паспорт",
    "жалақы",
    "身份证",
    "工资",
    "银行卡",
)


class VectorMemoryUnavailableError(Exception):
    """Vector memory backend or embedding provider is unavailable."""


class GeminiEmbeddingClient:
    """Small REST client for Gemini embeddings."""

    def __init__(self) -> None:
        api_key = get_gemini_embedding_api_key()
        if not api_key:
            raise VectorMemoryUnavailableError("A Gemini API key must be set for vector memory embeddings")
        self._api_key = api_key
        self._model = VECTOR_MEMORY_EMBEDDING_MODEL
        self._dimensions = VECTOR_MEMORY_DIMENSIONS

    def _content_for_task(self, text: str, *, task_type: str) -> str:
        if self._model == "gemini-embedding-2":
            if task_type == "RETRIEVAL_DOCUMENT":
                return f"title: group memory | text: {text}"
            if task_type == "RETRIEVAL_QUERY":
                return f"task: question answering | query: {text}"
            return f"task: search result | query: {text}"
        return text

    def embed(self, text: str, *, task_type: str) -> list[float]:
        cleaned = " ".join((text or "").split())
        if not cleaned:
            return []
        content_text = self._content_for_task(cleaned, task_type=task_type)
        payload: dict[str, Any] = {
            "content": {"parts": [{"text": content_text[:4000]}]},
        }
        if self._model == "gemini-embedding-2":
            payload["output_dimensionality"] = self._dimensions
        else:
            payload["taskType"] = task_type
            payload["outputDimensionality"] = self._dimensions
        url = f"{GEMINI_API_BASE}/{self._model}:embedContent?key={self._api_key}"
        try:
            resp = _http.request(
                "POST",
                url,
                body=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                retries=False,
            )
        except (HTTPError, OSError) as exc:
            raise VectorMemoryUnavailableError(f"Gemini embedding request failed: {exc}") from exc

        if resp.status >= 400:
            raise VectorMemoryUnavailableError(f"Gemini embedding API {resp.status}: {resp.data[:200]!r}")

        try:
            data = json.loads(resp.data.decode("utf-8"))
            values = data.get("embedding", {}).get("values")
            if values is None and data.get("embeddings"):
                values = data["embeddings"][0].get("values")
            vector = [float(value) for value in values]
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise VectorMemoryUnavailableError(f"Bad Gemini embedding response: {exc}") from exc
        if len(vector) != self._dimensions:
            raise VectorMemoryUnavailableError(
                f"Gemini embedding returned {len(vector)} dimensions, expected {self._dimensions}"
            )
        return vector


def _get_embedding_client() -> GeminiEmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = GeminiEmbeddingClient()
    return _embedding_client


def vector_memory_configured() -> bool:
    if not VECTOR_MEMORY_ENABLED or VECTOR_MEMORY_PROVIDER.strip().lower() != "s3_vectors":
        return False
    return S3VectorMemoryRepository().is_configured


def memory_vector_key(chat_id: int | str, source_sk: str) -> str:
    digest = hashlib.sha256(f"{chat_id}:{source_sk}".encode("utf-8")).hexdigest()
    return f"memory/{digest}"


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _safe_text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _list_text(value: Any, *, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw in value:
        text = _safe_text(raw, limit=120)
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def looks_sensitive_for_embedding(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(
        _EMAIL_RE.search(text or "")
        or _PHONE_RE.search(text or "")
        or _SECRET_ASSIGNMENT_RE.search(text or "")
        or any(cue in lowered for cue in _SENSITIVE_CUES)
        or (any(cue in lowered for cue in _SECRET_CUES) and _LONG_SECRET_RE.search(text or ""))
    )


def _within_distance(row: dict[str, Any], *, max_distance: float) -> bool:
    distance = row.get("distance")
    return not isinstance(distance, int | float) or float(distance) <= max_distance


def _distance_log_fields(rows: list[dict[str, Any]]) -> dict[str, float]:
    distances = [float(row["distance"]) for row in rows if isinstance(row.get("distance"), int | float)]
    if not distances:
        return {}
    return {
        "min_distance": round(min(distances), 4),
        "max_distance_seen": round(max(distances), 4),
    }


def build_embedding_document(item: dict[str, Any]) -> str:
    """Render a trusted memory item into compact text for embedding."""
    kind = str(item.get("kind") or "memory")
    sk = str(item.get("sk") or "")
    if sk.startswith("DAILY_SUMMARY#"):
        parts = [
            f"Daily group memory summary for {item.get('summary_date') or sk.removeprefix('DAILY_SUMMARY#')}.",
            _safe_text(item.get("summary"), limit=1200),
        ]
        for field, label in (
            ("topics", "Topics"),
            ("notable_events", "Notable events"),
            ("inside_jokes", "Inside jokes"),
            ("tension_points", "Tension points"),
        ):
            values = _list_text(item.get(field))
            if values:
                parts.append(f"{label}: {', '.join(values)}.")
        return "\n".join(part for part in parts if part)

    summary = _safe_text(item.get("summary") or item.get("text"), limit=900)
    speaker = _safe_text(item.get("display_name") or item.get("username") or item.get("user_id"), limit=80)
    reason = _safe_text(item.get("reason"), limit=160)
    parts = [f"Long-term group memory kind: {kind}."]
    if speaker:
        parts.append(f"Speaker: {speaker}.")
    if reason:
        parts.append(f"Why stored: {reason}.")
    if summary:
        parts.append(summary)
    return "\n".join(parts)


def _metadata_for_item(chat_id: int | str, source_sk: str, item: dict[str, Any], text: str) -> dict[str, Any]:
    created_at = item.get("created_at") or item.get("timestamp") or 0
    kind = str(item.get("kind") or "memory")
    metadata: dict[str, Any] = {
        "chat_id": str(chat_id),
        "memory_id": memory_vector_key(chat_id, source_sk),
        "source_sk": source_sk,
        "memory_kind": kind,
        "text": text[:1400],
        "created_at": int(created_at) if str(created_at).isdigit() else str(created_at or ""),
        "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
    }
    for field in ("user_id", "display_name", "username", "language", "summary_date"):
        value = item.get(field)
        if value not in (None, ""):
            metadata[field] = str(value)[:160]
    if item.get("confidence") is not None:
        metadata["importance_score"] = float(_plain(item["confidence"]))
    return metadata


def index_memory_item(
    chat_id: int | str,
    source_sk: str,
    *,
    repo: GroupMemoryRepository | None = None,
    vector_repo: S3VectorMemoryRepository | None = None,
    embedding_client: GeminiEmbeddingClient | None = None,
) -> bool:
    """Embed and index one long-term memory item by DynamoDB sort key."""
    repo = repo or GroupMemoryRepository()
    if not vector_memory_configured():
        logger.info(
            "Vector memory indexing skipped",
            extra={
                "chat_id": chat_id,
                "sk": source_sk,
                "reason": "not_configured",
                "provider": VECTOR_MEMORY_PROVIDER,
            },
        )
        return False
    if not GroupMemoryRepository.is_vectorizable_sk(source_sk):
        logger.info(
            "Vector memory indexing skipped",
            extra={"chat_id": chat_id, "sk": source_sk, "reason": "non_vectorizable_sk"},
        )
        return False

    item = repo.get_memory_item(chat_id, source_sk)
    if not item:
        logger.info(
            "Vector memory indexing skipped",
            extra={"chat_id": chat_id, "sk": source_sk, "reason": "missing_source_item"},
        )
        return False

    text = build_embedding_document(item)
    vector_key = str(item.get("vector_key") or memory_vector_key(chat_id, source_sk))
    skip_reason = ""
    if not text:
        skip_reason = "empty_document"
    elif looks_sensitive_for_embedding(text):
        skip_reason = "sensitive_document"
    elif not is_memory_learning_safe(text):
        skip_reason = "unsafe_memory"
    if skip_reason:
        repo.mark_vector_status(
            chat_id,
            source_sk,
            status="skipped",
            vector_key=vector_key,
            embedding_model=VECTOR_MEMORY_EMBEDDING_MODEL,
            dimensions=VECTOR_MEMORY_DIMENSIONS,
        )
        logger.info(
            "Vector memory indexing skipped",
            extra={
                "chat_id": chat_id,
                "sk": source_sk,
                "reason": skip_reason,
                "vector_key": vector_key,
                "memory_kind": str(item.get("kind") or ""),
                "text_chars": len(text),
            },
        )
        return False

    vector_repo = vector_repo or S3VectorMemoryRepository()
    embedding_client = embedding_client or _get_embedding_client()
    try:
        logger.info(
            "Vector memory indexing started",
            extra={
                "chat_id": chat_id,
                "sk": source_sk,
                "vector_key": vector_key,
                "memory_kind": str(item.get("kind") or ""),
                "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
                "dimensions": VECTOR_MEMORY_DIMENSIONS,
                "text_chars": len(text),
            },
        )
        if VECTOR_MEMORY_INDEX_THROTTLE_SECONDS > 0:
            time.sleep(VECTOR_MEMORY_INDEX_THROTTLE_SECONDS)
        vector = embedding_client.embed(text, task_type="RETRIEVAL_DOCUMENT")
        logger.info(
            "Vector memory document embedding generated",
            extra={
                "chat_id": chat_id,
                "sk": source_sk,
                "vector_key": vector_key,
                "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
                "vector_dimension_count": len(vector),
            },
        )
        vector_repo.put_memory_vector(
            key=vector_key,
            vector=vector,
            metadata=_metadata_for_item(chat_id, source_sk, item, text),
        )
        repo.mark_vector_status(
            chat_id,
            source_sk,
            status="indexed",
            vector_key=vector_key,
            embedding_model=VECTOR_MEMORY_EMBEDDING_MODEL,
            dimensions=VECTOR_MEMORY_DIMENSIONS,
        )
        logger.info(
            "Vector memory indexed",
            extra={
                "chat_id": chat_id,
                "sk": source_sk,
                "vector_key": vector_key,
                "memory_kind": str(item.get("kind") or ""),
                "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
                "dimensions": VECTOR_MEMORY_DIMENSIONS,
            },
        )
        return True
    except Exception as exc:
        repo.mark_vector_status(
            chat_id,
            source_sk,
            status="failed",
            vector_key=vector_key,
            error=str(exc),
            embedding_model=VECTOR_MEMORY_EMBEDDING_MODEL,
            dimensions=VECTOR_MEMORY_DIMENSIONS,
        )
        logger.exception("Vector memory indexing failed", extra={"chat_id": chat_id, "sk": source_sk})
        raise


def retrieve_relevant_memories(
    chat_id: int | str,
    query: str,
    limit: int = 8,
    *,
    user_id: int | str | None = None,
    memory_kinds: tuple[str, ...] | list[str] | None = None,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """Return semantic long-term memories relevant to a query; failures fall back to empty context."""
    query_chars = len(query.strip())
    if not vector_memory_configured():
        logger.info(
            "Vector memory retrieval skipped",
            extra={
                "chat_id": chat_id,
                "reason": "not_configured",
                "provider": VECTOR_MEMORY_PROVIDER,
                "query_chars": query_chars,
                "limit": limit,
            },
        )
        return []
    if not query.strip():
        logger.info(
            "Vector memory retrieval skipped",
            extra={"chat_id": chat_id, "reason": "empty_query", "limit": limit},
        )
        return []
    threshold = VECTOR_MEMORY_MAX_DISTANCE if max_distance is None else max_distance
    kinds = [str(kind) for kind in (memory_kinds or []) if str(kind)]
    try:
        logger.info(
            "Vector memory retrieval started",
            extra={
                "chat_id": chat_id,
                "query_chars": query_chars,
                "limit": limit,
                "max_distance": threshold,
                "user_filter_applied": user_id is not None,
                "memory_kinds": kinds,
                "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
            },
        )
        query_vector = _get_embedding_client().embed(query, task_type="RETRIEVAL_QUERY")
        logger.info(
            "Vector memory query embedding generated",
            extra={
                "chat_id": chat_id,
                "embedding_model": VECTOR_MEMORY_EMBEDDING_MODEL,
                "vector_dimension_count": len(query_vector),
            },
        )
        rows = S3VectorMemoryRepository().query(
            chat_id=chat_id,
            vector=query_vector,
            limit=limit,
            user_id=user_id,
            memory_kinds=memory_kinds,
        )
        filtered = [row for row in rows if _within_distance(row, max_distance=threshold)]
        logger.info(
            "Vector memory retrieval completed",
            extra={
                "chat_id": chat_id,
                "raw_count": len(rows),
                "returned_count": len(filtered),
                "distance_filtered_count": len(rows) - len(filtered),
                "max_distance": threshold,
                "user_filter_applied": user_id is not None,
                "memory_kinds": kinds,
                **_distance_log_fields(rows),
            },
        )
        return filtered
    except Exception:
        logger.exception(
            "Vector memory retrieval failed",
            extra={
                "chat_id": chat_id,
                "query_chars": query_chars,
                "limit": limit,
                "max_distance": threshold,
                "user_filter_applied": user_id is not None,
                "memory_kinds": kinds,
            },
        )
        return []


def format_semantic_memory_context(memories: list[dict[str, Any]]) -> str:
    """Render vector results as a distinct prompt section."""
    lines: list[str] = []
    for row in memories:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        text = _safe_text(metadata.get("text"), limit=900)
        if not text or not is_memory_learning_safe(text):
            continue
        kind = _safe_text(metadata.get("memory_kind") or "memory", limit=40)
        source_sk = _safe_text(metadata.get("source_sk"), limit=120)
        speaker = _safe_text(
            metadata.get("display_name") or metadata.get("username") or metadata.get("user_id"), limit=80
        )
        distance = row.get("distance")
        bits = [f"kind={kind}"]
        if source_sk:
            bits.append(f"source={source_sk}")
        if speaker:
            bits.append(f"speaker={speaker}")
        if isinstance(distance, int | float):
            bits.append(f"distance={distance:.4f}")
        lines.append(f"[semantic_memory {' '.join(bits)}] {text}")
    return "\n".join(lines)


def _vector_keys_for_items(chat_id: int | str, items: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for item in items:
        source_sk = str(item.get("sk") or "")
        if not source_sk:
            continue
        keys.append(str(item.get("vector_key") or memory_vector_key(chat_id, source_sk)))
    return keys


def delete_chat_vectors(
    chat_id: int | str,
    *,
    repo: GroupMemoryRepository | None = None,
    vector_repo: S3VectorMemoryRepository | None = None,
) -> int:
    if not vector_memory_configured():
        return 0
    repo = repo or GroupMemoryRepository()
    vector_repo = vector_repo or S3VectorMemoryRepository()
    deleted = 0
    start_key: dict[str, Any] | None = None
    while True:
        items, start_key = repo.list_vectorizable_memory_items(chat_id, limit=100, start_key=start_key)
        deleted += vector_repo.delete_vectors(_vector_keys_for_items(chat_id, items))
        if not start_key:
            return deleted


def delete_user_vectors(
    chat_id: int | str,
    user_id: int | str,
    *,
    repo: GroupMemoryRepository | None = None,
    vector_repo: S3VectorMemoryRepository | None = None,
) -> int:
    if not vector_memory_configured():
        return 0
    repo = repo or GroupMemoryRepository()
    vector_repo = vector_repo or S3VectorMemoryRepository()
    deleted = 0
    start_key: dict[str, Any] | None = None
    while True:
        items, start_key = repo.list_vectorizable_memory_items(
            chat_id,
            limit=100,
            start_key=start_key,
            user_id=user_id,
        )
        deleted += vector_repo.delete_vectors(_vector_keys_for_items(chat_id, items))
        if not start_key:
            return deleted


def get_vector_index_status(
    chat_id: int | str,
    *,
    repo: GroupMemoryRepository | None = None,
    overview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo = repo or GroupMemoryRepository()
    overview = overview or repo.get_memory_overview(chat_id)
    configured = vector_memory_configured()
    index_available = False
    if configured:
        try:
            index_available = bool(S3VectorMemoryRepository().get_index())
        except Exception:
            logger.exception("Vector memory index status check failed", extra={"chat_id": chat_id})
    return {
        "configured": configured,
        "provider": VECTOR_MEMORY_PROVIDER if configured else "",
        "index_available": index_available,
        "indexed_count": int(overview.get("vector_indexed") or 0),
        "failed_count": int(overview.get("vector_failed") or 0),
        "pending_count": int(overview.get("vector_pending") or 0),
        "skipped_count": int(overview.get("vector_skipped") or 0),
        "total_count": int(overview.get("vector_total") or 0),
        "last_backfill_status": overview.get("vector_backfill_status") or "",
        "last_backfill_updated_at": overview.get("vector_backfill_updated_at") or "",
        "last_backfill_failures": int(overview.get("vector_backfill_failures") or 0),
    }


def process_vector_memory_task(body: dict[str, Any], *, repo: GroupMemoryRepository | None = None) -> None:
    try:
        chat_id = body["chat_id"]
        source_sk = str(body["source_sk"])
    except KeyError as exc:
        logger.warning("PROCESS_VECTOR_MEMORY missing required field", extra={"missing": str(exc)})
        return
    index_memory_item(chat_id, source_sk, repo=repo)


def process_vector_memory_backfill_task(
    body: dict[str, Any],
    *,
    repo: GroupMemoryRepository | None = None,
    sqs_repo: Any | None = None,
) -> None:
    """Queue vector indexing tasks for one DynamoDB page of existing memories."""
    repo = repo or GroupMemoryRepository()
    if not vector_memory_configured():
        logger.info("Vector memory backfill skipped because vector memory is not configured")
        return
    chat_id = body.get("chat_id")
    if chat_id is None:
        logger.warning("PROCESS_VECTOR_MEMORY_BACKFILL missing chat_id")
        return
    limit = int(body.get("limit") or VECTOR_MEMORY_BACKFILL_BATCH_SIZE)
    start_key = body.get("start_key")
    start_key = start_key if isinstance(start_key, dict) else None
    items, next_key = repo.list_vectorizable_memory_items(chat_id, limit=limit, start_key=start_key)

    if sqs_repo is None:
        from services.repositories.sqs import SQSClient

        sqs_repo = SQSClient()

    enqueued = 0
    failures = 0
    for item in items:
        source_sk = str(item.get("sk") or "")
        if not source_sk:
            continue
        try:
            sqs_repo.send_vector_memory_task(chat_id=chat_id, source_sk=source_sk, reason="backfill")
            enqueued += 1
        except Exception:
            failures += 1
            logger.exception("Failed to enqueue vector memory backfill item", extra={"chat_id": chat_id})

    status = "queued_next_page" if next_key else "queued"
    if failures:
        status = "queued_with_failures"
    repo.record_vector_backfill_status(
        chat_id,
        status=status,
        processed=len(items),
        enqueued=enqueued,
        failures=failures,
        next_token=next_key,
    )
    if next_key:
        sqs_repo.send_vector_memory_backfill_task(chat_id=chat_id, limit=limit, start_key=next_key)
    logger.info(
        "Vector memory backfill page queued",
        extra={"chat_id": chat_id, "processed": len(items), "enqueued": enqueued, "has_next": bool(next_key)},
    )
