from unittest.mock import MagicMock

from services.repositories import group_memory as group_memory_repository
from services.repositories.group_memory import GroupMemoryRepository

_NOW = 1_700_000_000
_DAY = 24 * 60 * 60


def _repo() -> GroupMemoryRepository:
    repo = GroupMemoryRepository.__new__(GroupMemoryRepository)
    repo.table = MagicMock()
    return repo


def test_group_memory_repository_uses_type_specific_retention_days(monkeypatch):
    repo = _repo()
    monkeypatch.setattr(group_memory_repository.time, "time", lambda: _NOW)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS", 11)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS", 7)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS", 365)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS", 120)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS", 4)

    repo.store_message(
        chat_id=-100123,
        message_id=10,
        user_id=42,
        display_name="Ada",
        username=None,
        text="short raw context",
        created_at=_NOW,
        touch_profile=False,
    )
    item = repo.table.put_item.call_args.kwargs["Item"]
    assert item["sk"] == "MSG#1700000000000#10"
    assert item["ttl"] == _NOW + 11 * _DAY

    repo.table.put_item.reset_mock()
    item = repo.store_long_term_memory(
        chat_id=-100123,
        message_id=11,
        user_id=42,
        display_name="Ada",
        username=None,
        text="We decided to use S3 Vectors.",
        kind="group_fact",
        summary="The group decided to use S3 Vectors.",
        reason="explicit decision",
        confidence=0.88,
        created_at=_NOW,
    )
    assert item["sk"] == "GROUP_FACT#1700000000000#11"
    assert item["ttl"] == _NOW + 365 * _DAY

    repo.table.put_item.reset_mock()
    item = repo.store_daily_summary(
        chat_id=-100123,
        summary_date="2026-06-13",
        summary="Daily summary",
        topics=["memory"],
        notable_events=[],
        inside_jokes=[],
        active_participants=["Ada"],
        tension_points=[],
        message_count=12,
        source="gemini",
    )
    assert item["sk"] == "DAILY_SUMMARY#2026-06-13"
    assert item["ttl"] == _NOW + 120 * _DAY

    repo.table.put_item.reset_mock()
    repo.record_agent_reply(
        chat_id=-100123,
        bot_message_id=555,
        trigger_message_id=99,
        trigger_kind="explicit",
        reason="answered",
    )
    item = repo.table.put_item.call_args.kwargs["Item"]
    assert item["sk"] == "AGENT_REPLY#0000000000555"
    assert item["ttl"] == _NOW + 7 * _DAY

    assert repo.try_reserve_proactive_reply(-100123, daily_limit=3) is True
    values = repo.table.update_item.call_args.kwargs["ExpressionAttributeValues"]
    assert values[":ttl"] == _NOW + 4 * _DAY


def test_long_term_memory_ttl_keeps_shorter_explicit_expiry(monkeypatch):
    repo = _repo()
    monkeypatch.setattr(group_memory_repository.time, "time", lambda: _NOW)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS", 365)

    item = repo.store_long_term_memory(
        chat_id=-100123,
        message_id=11,
        user_id=42,
        display_name="Ada",
        username=None,
        text="Temporary launch window is next week.",
        kind="event",
        summary="Temporary launch window is next week.",
        reason="time-bound",
        confidence=0.7,
        created_at=_NOW,
        expires_in_days=5,
    )

    assert item["expires_at"] == _NOW + 5 * _DAY
    assert item["ttl"] == item["expires_at"]


def test_long_term_memory_ttl_caps_long_explicit_expiry_to_retention(monkeypatch):
    repo = _repo()
    monkeypatch.setattr(group_memory_repository.time, "time", lambda: _NOW)
    monkeypatch.setattr(group_memory_repository, "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS", 10)

    item = repo.store_long_term_memory(
        chat_id=-100123,
        message_id=11,
        user_id=42,
        display_name="Ada",
        username=None,
        text="This durable fact should still obey configured retention.",
        kind="group_fact",
        summary="The group has a durable fact.",
        reason="explicit fact",
        confidence=0.7,
        created_at=_NOW,
        expires_in_days=30,
    )

    assert item["expires_at"] == _NOW + 30 * _DAY
    assert item["ttl"] == _NOW + 10 * _DAY
