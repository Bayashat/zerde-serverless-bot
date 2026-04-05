"""Tests for ban-related stats in StatsRepository."""

import os
from unittest.mock import MagicMock, patch

import pytest

# Set required environment variables before importing anything from services
os.environ["BOT_TOKEN"] = "test_token"
os.environ["WEBHOOK_SECRET_TOKEN"] = "test_secret"
os.environ["QUEUE_URL"] = "test_queue"
os.environ["STATS_TABLE_NAME"] = "test_stats_table"


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
