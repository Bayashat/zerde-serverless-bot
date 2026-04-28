"""Shared test fixtures for the bot Lambda tests."""

import os
import sys
from unittest.mock import MagicMock

# Shared layer package (``zerde_common``) — same as ``/opt/python`` on Lambda
_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_ROOT, "src", "shared", "python"))

import pytest  # noqa: E402

# Set required env vars BEFORE importing bot modules
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "test-webhook-secret")
os.environ.setdefault("QUEUE_URL", "https://sqs.eu-central-1.amazonaws.com/123456789/test-queue")
os.environ.setdefault("STATS_TABLE_NAME", "test-stats-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")
os.environ.setdefault("TABLE_NAME", "test-quiz-table")
os.environ.setdefault("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-api-key")
os.environ.setdefault("DEFAULT_LANG", "kk")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("ADMIN_USER_ID", "1")
os.environ.setdefault("GEMINI_RPD_LIMIT", "1000")
os.environ.setdefault("CHAT_LANG_MAP", "{}")
os.environ.setdefault("CAPTCHA_TIMEOUT_SECONDS", "300")
os.environ.setdefault("KICK_BAN_DURATION_SECONDS", "60")
os.environ.setdefault("VOTEBAN_THRESHOLD", "5")
os.environ.setdefault("VOTEBAN_FORGIVE_THRESHOLD", "3")
os.environ.setdefault("CAPTCHA_MAX_ATTEMPTS", "3")
os.environ.setdefault("GROQ_API_KEY", "test-groq-api-key")
os.environ.setdefault("GROQ_MODEL", "test-groq-model")
os.environ.setdefault("DEEPSEEK_MODEL", "test-deepseek-model")
os.environ.setdefault("WTF_GEMINI_MODEL", "test-gemini-model")
os.environ.setdefault("QUIZ_LAMBDA_NAME", "test-quiz-lambda")

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
