"""Tests for quiz streak calculation logic."""

from unittest.mock import MagicMock, patch

FROZEN_TODAY = "2025-07-15"
FROZEN_YESTERDAY = "2025-07-14"
FROZEN_TWO_DAYS_AGO = "2025-07-13"

_PATCH_TODAY = patch("services.repositories.quiz._today_almaty", return_value=FROZEN_TODAY)
_PATCH_YESTERDAY = patch("services.repositories.quiz._yesterday_almaty", return_value=FROZEN_YESTERDAY)


class TestStreakCorrectAnswer:
    """Test update_score_correct streak logic."""

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_first_correct_answer_streak_is_1(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table
        mock_table.get_item.return_value = {}  # No existing record

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(return_value=None)
        repo.update_score_correct("chat1", "user1", "Test")

        put_call = mock_table.put_item.call_args
        item = put_call[1]["Item"]
        assert item["total_score"] == 1
        assert item["current_streak"] == 1
        assert item["best_streak"] == 1

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_consecutive_day_streak_increments(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 5,
                "current_streak": 3,
                "best_streak": 3,
                "last_correct_date": FROZEN_YESTERDAY,
                "last_answered_date": FROZEN_YESTERDAY,
                "first_name": "Test",
            }
        )
        repo.update_score_correct("chat1", "user1", "Test")

        put_call = mock_table.put_item.call_args
        item = put_call[1]["Item"]
        assert item["total_score"] == 6
        assert item["current_streak"] == 4
        assert item["best_streak"] == 4

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_gap_resets_streak_to_1(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 10,
                "current_streak": 5,
                "best_streak": 8,
                "last_correct_date": FROZEN_TWO_DAYS_AGO,
                "last_answered_date": FROZEN_TWO_DAYS_AGO,
                "first_name": "Test",
            }
        )
        repo.update_score_correct("chat1", "user1", "Test")

        put_call = mock_table.put_item.call_args
        item = put_call[1]["Item"]
        assert item["total_score"] == 11
        assert item["current_streak"] == 1
        assert item["best_streak"] == 8  # Preserved

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_duplicate_correct_same_day_is_noop(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 5,
                "current_streak": 3,
                "best_streak": 3,
                "last_correct_date": FROZEN_TODAY,
                "last_answered_date": FROZEN_TODAY,
                "first_name": "Test",
            }
        )
        repo.update_score_correct("chat1", "user1", "Test")

        mock_table.put_item.assert_not_called()


class TestStreakWrongAnswer:
    """Test update_score_wrong streak logic."""

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_wrong_answer_resets_streak(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 5,
                "current_streak": 3,
                "best_streak": 7,
                "last_correct_date": FROZEN_YESTERDAY,
                "last_answered_date": FROZEN_YESTERDAY,
                "first_name": "Test",
            }
        )
        repo.update_score_wrong("chat1", "user1", "Test")

        put_call = mock_table.put_item.call_args
        item = put_call[1]["Item"]
        assert item["total_score"] == 5  # Unchanged
        assert item["current_streak"] == 0
        assert item["best_streak"] == 7  # Preserved

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_duplicate_wrong_same_day_is_noop(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 5,
                "current_streak": 0,
                "best_streak": 3,
                "last_correct_date": FROZEN_YESTERDAY,
                "last_answered_date": FROZEN_TODAY,
                "first_name": "Test",
            }
        )
        repo.update_score_wrong("chat1", "user1", "Test")

        mock_table.put_item.assert_not_called()
