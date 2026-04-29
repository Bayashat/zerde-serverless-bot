"""Tests for quiz poll_answer and /quizstats handlers."""

import os
import sys
from unittest.mock import MagicMock

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
    def _make_ctx(self, poll_id, user_id, option_id, quiz_repo):
        update = {
            "poll_answer": {
                "poll_id": poll_id,
                "user": {"id": user_id, "first_name": "Test"},
                "option_ids": [option_id],
            }
        }
        bot = MagicMock()
        ctx = Context(update, bot, quiz_repo=quiz_repo)
        return ctx

    # def test_correct_answer_updates_score(self):
    #     quiz_repo = MagicMock()
    #     quiz_repo.lookup_poll.return_value = {
    #         "PK": "QUIZ#-100123",
    #         "SK": "DATE#2026-04-05",
    #         "correct_option_id": 2,
    #     }
    #     ctx = self._make_ctx("poll123", 456, 2, quiz_repo)

    #     handle_poll_answer(ctx)

    #     quiz_repo.update_score_correct.assert_called_once_with("-100123", "456", "Test")

    def test_wrong_answer_updates_score(self):
        quiz_repo = MagicMock()
        quiz_repo.lookup_poll.return_value = {
            "PK": "QUIZ#-100123",
            "SK": "DATE#2026-04-05",
            "correct_option_id": 2,
        }
        ctx = self._make_ctx("poll123", 456, 0, quiz_repo)

        handle_poll_answer(ctx)

        quiz_repo.update_score_wrong.assert_called_once_with("-100123", "456", "Test")

    def test_unknown_poll_id_ignored(self):
        quiz_repo = MagicMock()
        quiz_repo.lookup_poll.return_value = None
        ctx = self._make_ctx("unknown_poll", 456, 0, quiz_repo)

        handle_poll_answer(ctx)

        quiz_repo.update_score_correct.assert_not_called()
        quiz_repo.update_score_wrong.assert_not_called()

    def test_no_quiz_repo_skips(self):
        update = {
            "poll_answer": {
                "poll_id": "poll123",
                "user": {"id": 456, "first_name": "Test"},
                "option_ids": [0],
            }
        }
        bot = MagicMock()
        ctx = Context(update, bot)  # No quiz_repo
        handle_poll_answer(ctx)  # Should not raise


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
        assert "Season wins: <b>1</b>" in call_text
        assert "3</b> days" in call_text  # streak
        assert "#2</b>" in call_text  # rank

    def test_shows_no_data_for_new_user(self):
        quiz_repo = MagicMock()
        quiz_repo.get_user_score.return_value = None
        ctx = self._make_ctx(-100123, 456, quiz_repo)

        handle_quizstats(ctx)

        ctx.bot.send_message.assert_called_once()
        call_text = ctx.bot.send_message.call_args[0][1]
        assert "haven't answered" in call_text
