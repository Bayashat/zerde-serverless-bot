import os
from argparse import Namespace
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from botocore.exceptions import ClientError
from services.group_memory_processor import MemoryClassification
from services.history_import import (
    HistoryImportOptions,
    HistoryImportStats,
    _enqueue_vector,
    build_history_daily_summary,
    import_telegram_history,
    normalise_export_user_id,
    parse_telegram_export_messages,
    text_from_telegram_export,
)
from services.repositories.group_memory import GroupMemoryRepository

from dev.tools import import_telegram_history as import_tool


def _ts(day: str, hour: int = 12) -> int:
    year, month, date_day = (int(part) for part in day.split("-"))
    return int(datetime(year, month, date_day, hour, tzinfo=UTC).timestamp())


def _export(messages: list[dict]) -> dict:
    return {"name": "test group", "type": "public_supergroup", "messages": messages}


def test_text_from_telegram_export_flattens_rich_text():
    assert (
        text_from_telegram_export(["We decided to use ", {"type": "bold", "text": "S3 Vectors"}, "."])
        == "We decided to use S3 Vectors."
    )


def test_parse_telegram_export_messages_filters_range_commands_and_sensitive():
    stats = None
    data = _export(
        [
            {"id": 1, "type": "message", "date_unixtime": str(_ts("2025-12-31")), "from": "Ada", "text": "old"},
            {"id": 2, "type": "service", "date_unixtime": str(_ts("2026-01-01")), "text": "joined"},
            {"id": 3, "type": "message", "date_unixtime": str(_ts("2026-01-01")), "from": "Ada", "text": "/ask hi"},
            {
                "id": 4,
                "type": "message",
                "date_unixtime": str(_ts("2026-01-01")),
                "from": "Ada",
                "text": "password: super-secret",
            },
            {
                "id": 5,
                "type": "message",
                "date_unixtime": str(_ts("2026-01-01")),
                "from": "Ada",
                "from_id": "user42",
                "text": ["We decided to use ", {"text": "S3 Vectors"}],
            },
        ]
    )

    messages = parse_telegram_export_messages(data, since=date(2026, 1, 1), stats=stats)

    assert len(messages) == 1
    assert messages[0].message_id == 5
    assert messages[0].user_id == "42"
    assert messages[0].text == "We decided to use S3 Vectors"


def test_normalise_export_user_id_is_stable_without_from_id():
    row = {"from": "Ada Lovelace"}

    assert normalise_export_user_id(row) == normalise_export_user_id(row)
    assert normalise_export_user_id(row).startswith("export:")


def test_build_history_daily_summary_uses_all_messages_and_classifications():
    data = _export(
        [
            {
                "id": 1,
                "type": "message",
                "date_unixtime": str(_ts("2026-01-01")),
                "from": "Ada",
                "text": "We decided to use S3 Vectors tomorrow",
            },
            {
                "id": 2,
                "type": "message",
                "date_unixtime": str(_ts("2026-01-01")),
                "from": "Timur",
                "text": "I prefer Python for Lambda scripts",
            },
        ]
    )
    messages = parse_telegram_export_messages(data, since=date(2026, 1, 1))
    classifications = [
        (
            messages[0],
            MemoryClassification(
                kind="group_fact",
                summary="We decided to use S3 Vectors",
                reason="group decision",
                confidence=0.72,
            ),
        )
    ]

    summary = build_history_daily_summary("2026-01-01", messages, classifications)

    assert "imported 2 Telegram export messages" in summary["summary"]
    assert "Ada" in summary["active_participants"]
    assert "Timur" in summary["active_participants"]
    assert "vectors" in summary["topics"]
    assert summary["notable_events"] == ["We decided to use S3 Vectors"]


def test_import_cli_parses_vectorize_daily_summaries_flag(monkeypatch):
    monkeypatch.setattr(
        import_tool.sys,
        "argv",
        [
            "import_telegram_history.py",
            "--chat-id",
            "-100123",
            "--export",
            "result.json",
            "--vectorize-daily-summaries",
        ],
    )

    args = import_tool._parse_args()

    assert args.vectorize_daily_summaries is True


def test_import_cli_seeds_vector_queue_url(monkeypatch):
    for env_name in [
        "MEMORY_TABLE_NAME",
        "VECTOR_MEMORY_QUEUE_URL",
        "AWS_DEFAULT_REGION",
        "QUEUE_URL",
        "STATS_TABLE_NAME",
        "ADMIN_USER_ID",
        "GEMINI_RPD_LIMIT",
        "CHAT_LANG_MAP",
        "CAPTCHA_TIMEOUT_SECONDS",
        "KICK_BAN_DURATION_SECONDS",
        "VOTEBAN_THRESHOLD",
        "VOTEBAN_FORGIVE_THRESHOLD",
        "CAPTCHA_MAX_ATTEMPTS",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    import_tool._seed_required_env(
        Namespace(
            table_name="memory-table",
            queue_url="https://sqs.example/vector-memory",
            aws_region="eu-central-1",
        )
    )

    assert os.environ["MEMORY_TABLE_NAME"] == "memory-table"
    assert os.environ["VECTOR_MEMORY_QUEUE_URL"] == "https://sqs.example/vector-memory"
    assert os.environ["QUEUE_URL"].endswith("/history-import-dry-run")


def test_import_telegram_history_dry_run_does_not_write(tmp_path):
    export_path = tmp_path / "result.json"
    export_path.write_text(
        (
            '{"messages":['
            '{"id":1,"type":"message","date_unixtime":"1767272400","from":"Ada",'
            '"text":"We decided to use S3 Vectors tomorrow"}'
            "]}"
        ),
        encoding="utf-8",
    )
    repo = MagicMock()

    result = import_telegram_history(
        HistoryImportOptions(
            chat_id=-100123,
            export_path=export_path,
            since=date(2026, 1, 1),
            dry_run=True,
        ),
        repo=repo,
        vector_enqueue=MagicMock(),
    )

    assert result.stats.parsed_messages == 1
    assert result.stats.long_term_memories == 1
    assert result.stats.daily_summaries == 1
    repo.store_message.assert_not_called()
    repo.store_long_term_memory.assert_not_called()


def test_import_telegram_history_writes_memory_and_enqueues_vectors(tmp_path):
    export_path = tmp_path / "result.json"
    export_path.write_text(
        (
            '{"messages":['
            '{"id":1,"type":"message","date_unixtime":"1767272400","from":"Ada","from_id":"user42",'
            '"text":"We decided to use S3 Vectors tomorrow"},'
            '{"id":2,"type":"message","date_unixtime":"1767276000","from":"Timur","from_id":"user43",'
            '"text":"I prefer Python for Lambda scripts"}'
            "]}"
        ),
        encoding="utf-8",
    )
    repo = MagicMock()
    repo.store_message.return_value = True
    repo.store_long_term_memory.side_effect = [
        {"sk": "GROUP_FACT#1#1"},
        {"sk": "USER_FACT#43#2#2"},
    ]
    repo.store_daily_summary.return_value = {"sk": "DAILY_SUMMARY#2026-01-01"}
    vector_enqueue = MagicMock()

    result = import_telegram_history(
        HistoryImportOptions(
            chat_id=-100123,
            export_path=export_path,
            since=date(2026, 1, 1),
            dry_run=False,
        ),
        repo=repo,
        vector_enqueue=vector_enqueue,
    )

    assert result.stats.stored_messages == 2
    assert result.stats.long_term_by_kind["group_fact"] == 1
    assert result.stats.long_term_by_kind["user_fact"] == 1
    assert repo.store_message.call_count == 2
    assert repo.store_message.call_args_list[0].kwargs["skip_if_exists"] is True
    assert repo.store_long_term_memory.call_count == 2
    assert repo.store_daily_summary.call_args.kwargs["source"] == "telegram_export_import"
    assert [call.kwargs["source_sk"] for call in vector_enqueue.call_args_list] == [
        "GROUP_FACT#1#1",
        "USER_FACT#43#2#2",
    ]
    assert result.stats.vector_tasks == 2


def test_import_telegram_history_vectorizes_daily_summary_when_enabled(tmp_path):
    export_path = tmp_path / "result.json"
    export_path.write_text(
        (
            '{"messages":['
            '{"id":1,"type":"message","date_unixtime":"1767272400","from":"Ada","from_id":"user42",'
            '"text":"We decided to use S3 Vectors tomorrow"}'
            "]}"
        ),
        encoding="utf-8",
    )
    repo = MagicMock()
    repo.store_message.return_value = True
    repo.store_long_term_memory.return_value = {"sk": "GROUP_FACT#1#1"}
    repo.store_daily_summary.return_value = {"sk": "DAILY_SUMMARY#2026-01-01"}
    vector_enqueue = MagicMock()

    result = import_telegram_history(
        HistoryImportOptions(
            chat_id=-100123,
            export_path=export_path,
            since=date(2026, 1, 1),
            dry_run=False,
            vectorize_daily_summaries=True,
        ),
        repo=repo,
        vector_enqueue=vector_enqueue,
    )

    assert [call.kwargs["source_sk"] for call in vector_enqueue.call_args_list] == [
        "GROUP_FACT#1#1",
        "DAILY_SUMMARY#2026-01-01",
    ]
    assert result.stats.vector_tasks == 2


def test_history_import_skips_non_vectorizable_agent_reply_enqueue():
    vector_enqueue = MagicMock()
    stats = HistoryImportStats()

    _enqueue_vector(
        HistoryImportOptions(chat_id=-100123, export_path=MagicMock(), since=date(2026, 1, 1)),
        vector_enqueue,
        "AGENT_REPLY#0000000000555",
        stats,
    )

    vector_enqueue.assert_not_called()
    assert stats.vector_tasks == 0


def test_store_message_skip_if_exists_does_not_touch_profile():
    repo = GroupMemoryRepository.__new__(GroupMemoryRepository)
    repo.table = MagicMock()
    repo.table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
        "PutItem",
    )
    repo._touch_user_profile = MagicMock()

    stored = repo.store_message(
        chat_id=-100123,
        message_id=1,
        user_id=42,
        display_name="Ada",
        username=None,
        text="hello",
        created_at=_ts("2026-01-01"),
        skip_if_exists=True,
    )

    assert stored is False
    repo._touch_user_profile.assert_not_called()
