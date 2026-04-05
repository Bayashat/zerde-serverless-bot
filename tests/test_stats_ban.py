"""Tests for ban-related stats in StatsRepository."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def stats_repo(mock_table):
    with patch("services.repositories.stats.get_dynamodb") as mock_dynamo:
        mock_dynamo.return_value.Table.return_value = mock_table
        from services.repositories.stats import StatsRepository

        repo = StatsRepository()
        repo._table = mock_table
        return repo


def test_increment_total_bans_calls_update_item(stats_repo, mock_table):
    stats_repo.increment_total_bans(chat_id=123)
    mock_table.update_item.assert_called_once()
    call_kwargs = mock_table.update_item.call_args[1]
    assert call_kwargs["Key"] == {"stat_key": "123"}
    assert "total_bans" in call_kwargs["ExpressionAttributeNames"].values()


def test_get_stats_includes_total_bans(stats_repo, mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "total_joins": 10,
            "verified_users": 8,
            "total_bans": 3,
            "started_at": "2026-01-01 00:00:00 UTC+5",
        }
    }
    result = stats_repo.get_stats(chat_id=123)
    assert result["total_bans"] == 3


def test_get_stats_total_bans_defaults_to_zero(stats_repo, mock_table):
    mock_table.get_item.return_value = {"Item": {"total_joins": 5, "verified_users": 4, "started_at": "2026-01-01"}}
    result = stats_repo.get_stats(chat_id=123)
    assert result["total_bans"] == 0


def test_finalize_ban_increments_total_bans():
    """_finalize_ban should call stats_repo.increment_total_bans."""
    from services.handlers.voteban import _finalize_ban

    ctx = MagicMock()
    ctx.chat_id = -100123
    ctx.message_id = 999
    ctx.vote_repo.get_vote_session.return_value = {
        "target_username": "testuser",
        "target_first_name": "Test",
        "votes_for_info": [],
        "reply_message_id": 888,
    }

    _finalize_ban(ctx, target_user_id=42, votes_for=3)

    ctx.stats_repo.increment_total_bans.assert_called_once_with(ctx.chat_id)


def test_finalize_ban_handles_missing_stats_repo():
    """_finalize_ban should not raise when stats_repo is None."""
    from services.handlers.voteban import _finalize_ban

    ctx = MagicMock()
    ctx.chat_id = -100123
    ctx.message_id = 999
    ctx.stats_repo = None
    ctx.vote_repo.get_vote_session.return_value = {
        "target_username": "testuser",
        "target_first_name": "Test",
        "votes_for_info": [],
        "reply_message_id": 888,
    }

    _finalize_ban(ctx, target_user_id=42, votes_for=3)
    # No exception means the guard clause worked


def test_handle_stats_includes_banned_count():
    """handle_stats should pass banned count to the stats_message template."""
    from services.handlers.commands import handle_stats

    ctx = MagicMock()
    ctx.chat_id = -100123
    ctx.lang_code = "en"
    ctx.bot.get_chat_member.return_value = {"status": "administrator"}
    ctx.stats_repo.get_stats.return_value = {
        "total_joins": 20,
        "verified_users": 15,
        "total_bans": 5,
        "started_at": "2026-01-01 00:00:00 UTC+5",
    }

    with patch("services.handlers.commands.get_translated_text") as mock_t:
        mock_t.return_value = "stats text"
        handle_stats(ctx)

    calls = mock_t.call_args_list
    stats_call = next(c for c in calls if c.args[0] == "stats_message")
    assert stats_call.kwargs.get("banned") == 5
