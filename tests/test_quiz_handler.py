"""Tests for quiz poll_answer and /quizstats handlers."""

import os
import sys
from unittest.mock import MagicMock

import pytest
from services.repositories._quiz_answers import QuizAnswerRetryRequiredError

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "test-webhook-secret")
os.environ.setdefault("QUEUE_URL", "https://sqs.eu-central-1.amazonaws.com/123456789/test-queue")
os.environ.setdefault("STATS_TABLE_NAME", "test-stats-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "bot"))

from core import config as bot_config  # noqa: E402
from core.dispatcher import Context  # noqa: E402
from services.handlers.quiz import handle_poll_answer, handle_quizstats  # noqa: E402

# CHAT_LANG_MAP is read at first ``core.config`` import (often before this module's env runs).
_QUIZSTATS_TEST_CHAT_KEY = "-100123"
bot_config.CHAT_LANG_MAP[_QUIZSTATS_TEST_CHAT_KEY] = "en"


class TestHandlePollAnswer:
    def _ctx(self, quiz_repo):
        update = {"update_id": 123, "poll_answer": {"poll_id": "poll123", "user": {"id": 456}, "option_ids": [0]}}
        return Context(update, MagicMock(), quiz_repo=quiz_repo, sqs_repo=MagicMock())

    def test_persist_before_queue_and_no_inline_lookup(self):
        repo = MagicMock()
        repo.persist_answer.return_value = {"state": "PENDING", "poll_id": "poll123", "user_id": "456"}
        ctx = self._ctx(repo)
        handle_poll_answer(ctx)
        repo.persist_answer.assert_called_once_with(ctx.poll_answer, 123)
        repo.lookup_poll.assert_not_called()
        ctx.sqs_repo.send_quiz_answer_task.assert_called_once_with("poll123", "456")

    def test_enqueue_failure_keeps_durable_receipt(self):
        repo = MagicMock()
        repo.persist_answer.return_value = {"state": "PENDING", "poll_id": "poll123", "user_id": "456"}
        ctx = self._ctx(repo)
        ctx.sqs_repo.send_quiz_answer_task.side_effect = RuntimeError("synthetic")
        handle_poll_answer(ctx)
        repo.persist_answer.assert_called_once()

    def test_missing_repo_requires_webhook_redelivery(self):
        with pytest.raises(QuizAnswerRetryRequiredError):
            handle_poll_answer(self._ctx(None))

    def test_database_failure_requires_webhook_redelivery(self):
        repo = MagicMock()
        repo.persist_answer.side_effect = RuntimeError("synthetic")
        with pytest.raises(QuizAnswerRetryRequiredError):
            handle_poll_answer(self._ctx(repo))

    def test_terminal_duplicate_is_not_queued(self):
        repo = MagicMock()
        repo.persist_answer.return_value = {"state": "SCORED"}
        ctx = self._ctx(repo)
        handle_poll_answer(ctx)
        ctx.sqs_repo.send_quiz_answer_task.assert_not_called()


class TestHandleQuizstats:
    def _make_ctx(self, chat_id, user_id, quiz_repo):
        update = {
            "message": {
                "chat": {"id": chat_id},
                "from": {"id": user_id, "first_name": "Test", "language_code": "en"},
                "text": "/quizstats",
            }
        }
        bot = MagicMock()
        bot.send_message.return_value = {"message_id": 999}
        ctx = Context(update, bot, quiz_repo=quiz_repo)
        return ctx

    def test_shows_stats_for_existing_user(self):
        quiz_repo = MagicMock()
        quiz_repo.get_user_score.return_value = {
            "total_score": 10,
            "week_score": 4,
            "season_wins": 1,
            "current_streak": 3,
            "best_streak": 5,
        }
        quiz_repo.get_leaderboard.return_value = [
            {"SK": "USER#111", "week_score": 8},
            {"SK": "USER#456", "week_score": 4},
            {"SK": "USER#789", "week_score": 1},
        ]
        ctx = self._make_ctx(-100123, 456, quiz_repo)
        ctx.bot.get_chat.return_value = {
            "id": -100123,
            "type": "supergroup",
            "title": "Test Group",
            "username": "testgroup",
        }

        handle_quizstats(ctx)

        ctx.bot.send_message.assert_called_once()
        ctx.bot.get_chat.assert_called_once_with(-100123)
        call_text = ctx.bot.send_message.call_args[0][1]
        assert "Test Group" in call_text
        assert "@testgroup" in call_text
        assert "4 pts" in call_text  # week_score
        assert "10 pts" in call_text  # total_score (all-time)
        assert "This season weekly wins: <b>1/4</b>" in call_text
        assert "All-time season titles: <b>0</b>" in call_text
        assert "3</b> days" in call_text  # streak
        assert "#2</b>" in call_text  # rank

    def test_shows_no_data_for_new_user(self):
        quiz_repo = MagicMock()
        quiz_repo.get_user_score.return_value = None
        ctx = self._make_ctx(-100123, 456, quiz_repo)

        handle_quizstats(ctx)

        ctx.bot.send_message.assert_called_once()
        call_text = ctx.bot.send_message.call_args[0][1]
        assert "No quiz score yet" in call_text
