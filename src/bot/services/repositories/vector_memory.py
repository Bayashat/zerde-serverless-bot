"""S3 Vectors repository for semantic group memory retrieval."""

from __future__ import annotations

from typing import Any

import boto3
from core.config import (
    VECTOR_MEMORY_INDEX_NAME,
    VECTOR_MEMORY_PROVIDER,
    VECTOR_MEMORY_VECTOR_BUCKET_NAME,
)
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_S3_VECTORS_CLIENT = None


def _get_s3_vectors_client():
    global _S3_VECTORS_CLIENT
    if _S3_VECTORS_CLIENT is None:
        _S3_VECTORS_CLIENT = boto3.client("s3vectors")
    return _S3_VECTORS_CLIENT


class S3VectorMemoryRepository:
    """Thin adapter around the Amazon S3 Vectors API."""

    def __init__(
        self,
        *,
        vector_bucket_name: str | None = None,
        index_name: str | None = None,
    ) -> None:
        self.vector_bucket_name = vector_bucket_name or VECTOR_MEMORY_VECTOR_BUCKET_NAME
        self.index_name = index_name or VECTOR_MEMORY_INDEX_NAME

    @property
    def client(self):
        return _get_s3_vectors_client()

    @property
    def is_configured(self) -> bool:
        return bool(
            VECTOR_MEMORY_PROVIDER.strip().lower() == "s3_vectors" and self.vector_bucket_name and self.index_name
        )

    def put_memory_vector(
        self,
        *,
        key: str,
        vector: list[float],
        metadata: dict[str, Any],
    ) -> None:
        if not self.is_configured:
            raise ValueError("S3 vector memory is not configured")
        self.client.put_vectors(
            vectorBucketName=self.vector_bucket_name,
            indexName=self.index_name,
            vectors=[
                {
                    "key": key,
                    "data": {"float32": vector},
                    "metadata": metadata,
                }
            ],
        )

    def query(
        self,
        *,
        chat_id: int | str,
        vector: list[float],
        limit: int,
        user_id: int | str | None = None,
        memory_kinds: tuple[str, ...] | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.is_configured:
            return []
        filters: list[dict[str, Any]] = [{"chat_id": {"$eq": str(chat_id)}}]
        if user_id is not None:
            filters.append({"user_id": {"$eq": str(user_id)}})
        kinds = [str(kind) for kind in (memory_kinds or []) if str(kind)]
        if kinds:
            filters.append({"memory_kind": {"$in": kinds}})
        metadata_filter = filters[0] if len(filters) == 1 else {"$and": filters}
        resp = self.client.query_vectors(
            vectorBucketName=self.vector_bucket_name,
            indexName=self.index_name,
            topK=max(1, min(20, int(limit))),
            queryVector={"float32": vector},
            filter=metadata_filter,
            returnMetadata=True,
            returnDistance=True,
        )
        results: list[dict[str, Any]] = []
        for row in resp.get("vectors") or []:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            results.append(
                {
                    "key": row.get("key"),
                    "distance": row.get("distance"),
                    "metadata": metadata,
                }
            )
        return results

    def delete_vectors(self, keys: list[str]) -> int:
        if not self.is_configured or not keys:
            return 0
        deleted = 0
        for start in range(0, len(keys), 500):
            batch = keys[start : start + 500]
            self.client.delete_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=self.index_name,
                keys=batch,
            )
            deleted += len(batch)
        return deleted

    def list_vectors(
        self,
        *,
        limit: int = 100,
        next_token: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.is_configured:
            return [], None
        kwargs: dict[str, Any] = {
            "vectorBucketName": self.vector_bucket_name,
            "indexName": self.index_name,
            "maxResults": max(1, min(500, int(limit))),
            "returnMetadata": True,
        }
        if next_token:
            kwargs["nextToken"] = next_token
        resp = self.client.list_vectors(**kwargs)
        return resp.get("vectors") or [], resp.get("nextToken")

    def get_index(self) -> dict[str, Any]:
        if not self.is_configured:
            return {}
        resp = self.client.get_index(
            vectorBucketName=self.vector_bucket_name,
            indexName=self.index_name,
        )
        index = resp.get("index")
        return index if isinstance(index, dict) else {}
