"""Shared test fixtures for the bot Lambda tests."""

import os
import sys
from unittest.mock import MagicMock

import pytest

# Set required env vars BEFORE importing bot modules
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "test-webhook-secret")
os.environ.setdefault("QUEUE_URL", "https://sqs.eu-central-1.amazonaws.com/123456789/test-queue")
os.environ.setdefault("STATS_TABLE_NAME", "test-stats-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")
os.environ.setdefault("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
os.environ.setdefault("DEFAULT_LANG", "kk")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

# Add src/bot to sys.path so imports work like they do in Lambda
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "bot"))


@pytest.fixture
def mock_bot():
    """Mock TelegramClient with all methods stubbed."""
    bot = MagicMock()
    bot.send_message.return_value = {"message_id": 999}
    bot.get_chat_member.return_value = {"status": "member"}
    bot.answer_callback_query.return_value = None
    bot.restrict_chat_member.return_value = None
    bot.kick_chat_member.return_value = None
    bot.delete_message.return_value = None
    bot.edit_message_text.return_value = {}
    return bot


@pytest.fixture
def mock_stats_repo():
    """Mock StatsRepository."""
    repo = MagicMock()
    repo.get_stats.return_value = {
        "total_joins": 100,
        "verified_users": 75,
        "started_at": "2025-01-01 00:00:00 UTC+5",
    }
    return repo


@pytest.fixture
def mock_sqs_repo():
    """Mock SQSClient."""
    return MagicMock()


@pytest.fixture
def mock_vote_repo():
    """Mock VoteRepository."""
    return MagicMock()


@pytest.fixture
def mock_quiz_repo():
    """Mock QuizRepository."""
    repo = MagicMock()
    repo.lookup_poll.return_value = None
    repo.get_user_score.return_value = None
    repo.get_leaderboard.return_value = []
    return repo
