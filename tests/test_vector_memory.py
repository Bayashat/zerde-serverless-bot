from unittest.mock import MagicMock

from services import vector_memory
from services.repositories import vector_memory as vector_repo_module
from services.repositories.vector_memory import S3VectorMemoryRepository


def test_s3_vectors_repository_put_query_delete_and_list(monkeypatch):
    fake_client = MagicMock()
    fake_client.query_vectors.return_value = {
        "vectors": [
            {
                "key": "memory/abc",
                "distance": 0.12,
                "metadata": {"chat_id": "-100123", "text": "We chose S3 Vectors."},
            }
        ]
    }
    fake_client.list_vectors.return_value = {"vectors": [{"key": "memory/abc"}], "nextToken": "next"}
    fake_client.get_index.return_value = {"index": {"indexName": "idx"}}
    monkeypatch.setattr(vector_repo_module, "_S3_VECTORS_CLIENT", fake_client)
    monkeypatch.setattr(vector_repo_module, "VECTOR_MEMORY_PROVIDER", "s3_vectors")
    monkeypatch.setattr(vector_repo_module, "VECTOR_MEMORY_VECTOR_BUCKET_NAME", "bucket")
    monkeypatch.setattr(vector_repo_module, "VECTOR_MEMORY_INDEX_NAME", "idx")

    repo = S3VectorMemoryRepository()
    repo.put_memory_vector(key="memory/abc", vector=[0.1, 0.2], metadata={"chat_id": "-100123"})
    results = repo.query(chat_id=-100123, vector=[0.1, 0.2], limit=8)
    deleted = repo.delete_vectors(["memory/abc"])
    listed, token = repo.list_vectors(limit=10)

    fake_client.put_vectors.assert_called_once()
    fake_client.query_vectors.assert_called_once()
    assert fake_client.query_vectors.call_args.kwargs["filter"] == {"chat_id": {"$eq": "-100123"}}
    fake_client.delete_vectors.assert_called_once()
    assert deleted == 1
    assert results[0]["metadata"]["text"] == "We chose S3 Vectors."
    assert listed[0]["key"] == "memory/abc"
    assert token == "next"
    assert repo.get_index()["indexName"] == "idx"


def test_index_memory_item_skips_sensitive_content(monkeypatch):
    monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: True)
    repo = MagicMock()
    repo.get_memory_item.return_value = {
        "sk": "USER_FACT#42#1#2",
        "kind": "user_fact",
        "summary": "My api key is secret: abc123",
        "user_id": "42",
    }
    embedding = MagicMock()
    vector_repo = MagicMock()

    indexed = vector_memory.index_memory_item(
        -100123,
        "USER_FACT#42#1#2",
        repo=repo,
        vector_repo=vector_repo,
        embedding_client=embedding,
    )

    assert indexed is False
    embedding.embed.assert_not_called()
    vector_repo.put_memory_vector.assert_not_called()
    repo.mark_vector_status.assert_called_once()
    assert repo.mark_vector_status.call_args.kwargs["status"] == "skipped"


def test_embedding_privacy_guard_allows_dates_and_message_counts():
    text = (
        "Daily group memory summary for 2026-06-11. "
        "2026-06-11: imported 151187 Telegram export messages from 42 participants."
    )

    assert vector_memory.looks_sensitive_for_embedding(text) is False


def test_embedding_privacy_guard_still_blocks_phone_numbers():
    assert vector_memory.looks_sensitive_for_embedding("Call me at +7 777 123 45 67") is True


def test_gemini_embedding_2_formats_retrieval_tasks(monkeypatch):
    monkeypatch.setattr(vector_memory, "VECTOR_MEMORY_EMBEDDING_MODEL", "gemini-embedding-2")
    client = vector_memory.GeminiEmbeddingClient.__new__(vector_memory.GeminiEmbeddingClient)
    client._api_key = "test"
    client._model = "gemini-embedding-2"
    client._dimensions = 768

    assert client._content_for_task("What happened?", task_type="RETRIEVAL_QUERY").startswith(
        "task: question answering | query:"
    )
    assert client._content_for_task("A memory", task_type="RETRIEVAL_DOCUMENT").startswith(
        "title: group memory | text:"
    )


def test_index_memory_item_puts_gemini_embedding_to_vector_store(monkeypatch):
    monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: True)
    repo = MagicMock()
    repo.get_memory_item.return_value = {
        "sk": "EVENT#1#2",
        "kind": "event",
        "summary": "We decided to use S3 Vectors for memory retrieval.",
        "display_name": "Ada",
        "created_at": 1_700_000_000,
    }
    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 768
    vector_repo = MagicMock()

    indexed = vector_memory.index_memory_item(
        -100123,
        "EVENT#1#2",
        repo=repo,
        vector_repo=vector_repo,
        embedding_client=embedding,
    )

    assert indexed is True
    embedding.embed.assert_called_once()
    assert embedding.embed.call_args.kwargs["task_type"] == "RETRIEVAL_DOCUMENT"
    put_kwargs = vector_repo.put_memory_vector.call_args.kwargs
    assert put_kwargs["metadata"]["chat_id"] == "-100123"
    assert put_kwargs["metadata"]["source_sk"] == "EVENT#1#2"
    assert put_kwargs["metadata"]["memory_kind"] == "event"
    repo.mark_vector_status.assert_called_once()
    assert repo.mark_vector_status.call_args.kwargs["status"] == "indexed"


def test_retrieve_relevant_memories_uses_query_embedding(monkeypatch):
    monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: True)
    embedding = MagicMock()
    embedding.embed.return_value = [0.2] * 768
    vector_repo = MagicMock()
    vector_repo.query.return_value = [{"metadata": {"text": "S3 Vectors was selected."}}]
    monkeypatch.setattr(vector_memory, "_get_embedding_client", lambda: embedding)
    monkeypatch.setattr(vector_memory, "S3VectorMemoryRepository", lambda: vector_repo)

    results = vector_memory.retrieve_relevant_memories(-100123, "what did we pick?", limit=3)

    embedding.embed.assert_called_once_with("what did we pick?", task_type="RETRIEVAL_QUERY")
    vector_repo.query.assert_called_once_with(chat_id=-100123, vector=[0.2] * 768, limit=3)
    assert results[0]["metadata"]["text"] == "S3 Vectors was selected."


def test_semantic_memory_context_format_is_distinct():
    context = vector_memory.format_semantic_memory_context(
        [
            {
                "distance": 0.42,
                "metadata": {
                    "memory_kind": "daily_summary",
                    "source_sk": "DAILY_SUMMARY#2026-06-10",
                    "text": "The group compared vector stores.",
                },
            }
        ]
    )

    assert context.startswith("[semantic_memory kind=daily_summary")
    assert "DAILY_SUMMARY#2026-06-10" in context
    assert "The group compared vector stores." in context


def test_vector_backfill_batches_and_continues(monkeypatch):
    monkeypatch.setattr(vector_memory, "vector_memory_configured", lambda: True)
    repo = MagicMock()
    repo.list_vectorizable_memory_items.return_value = (
        [{"sk": "EVENT#1#2"}, {"sk": "DAILY_SUMMARY#2026-06-10"}],
        {"pk": "CHAT#-100123", "sk": "JOKE#3#4"},
    )
    sqs = MagicMock()

    vector_memory.process_vector_memory_backfill_task(
        {"chat_id": -100123, "limit": 2},
        repo=repo,
        sqs_repo=sqs,
    )

    assert sqs.send_vector_memory_task.call_count == 2
    sqs.send_vector_memory_backfill_task.assert_called_once_with(
        chat_id=-100123,
        limit=2,
        start_key={"pk": "CHAT#-100123", "sk": "JOKE#3#4"},
    )
    repo.record_vector_backfill_status.assert_called_once()
    assert repo.record_vector_backfill_status.call_args.kwargs["status"] == "queued_next_page"
