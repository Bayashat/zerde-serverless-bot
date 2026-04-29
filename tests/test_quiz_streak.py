"""Tests for quiz streak calculation logic."""

from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

FROZEN_TODAY = "2025-07-15"
FROZEN_YESTERDAY = "2025-07-14"
FROZEN_TWO_DAYS_AGO = "2025-07-13"

_PATCH_TODAY = patch("services.repositories.quiz._today_almaty", return_value=FROZEN_TODAY)
_PATCH_YESTERDAY = patch("services.repositories.quiz._yesterday_almaty", return_value=FROZEN_YESTERDAY)


def _conditional_check_failed():
    """Build a ClientError that mimics DynamoDB ConditionalCheckFailedException."""
    err = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "condition failed"}},
        "UpdateItem",
    )
    return err


class TestStreakCorrectAnswer:
    """Test update_score_correct streak logic."""

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_first_correct_answer_streak_is_1(self, mock_dynamo, _m_today, _m_yday):
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(return_value=None)
        repo.update_score_correct("chat1", "user1", "Test")

        mock_table.update_item.assert_called_once()
        vals = mock_table.update_item.call_args[1]["ExpressionAttributeValues"]
        assert vals[":pts"] == 1
        assert vals[":streak"] == 1
        assert vals[":best"] == 1

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
                "week_score": 3,
                "current_streak": 3,
                "best_streak": 3,
                "last_correct_date": FROZEN_YESTERDAY,
                "last_answered_date": FROZEN_YESTERDAY,
                "first_name": "Test",
            }
        )
        repo.update_score_correct("chat1", "user1", "Test")

        mock_table.update_item.assert_called_once()
        vals = mock_table.update_item.call_args[1]["ExpressionAttributeValues"]
        assert vals[":pts"] == 1
        assert vals[":streak"] == 4
        assert vals[":best"] == 4

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
                "week_score": 6,
                "current_streak": 5,
                "best_streak": 8,
                "last_correct_date": FROZEN_TWO_DAYS_AGO,
                "last_answered_date": FROZEN_TWO_DAYS_AGO,
                "first_name": "Test",
            }
        )
        repo.update_score_correct("chat1", "user1", "Test")

        mock_table.update_item.assert_called_once()
        vals = mock_table.update_item.call_args[1]["ExpressionAttributeValues"]
        assert vals[":pts"] == 1
        assert vals[":streak"] == 1
        assert vals[":best"] == 8  # Preserved

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_duplicate_correct_same_day_is_noop(self, mock_dynamo, _m_today, _m_yday):
        """DynamoDB ConditionExpression blocks the duplicate; the method must swallow it."""
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table
        mock_table.update_item.side_effect = _conditional_check_failed()

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        repo.get_user_score = MagicMock(
            return_value={
                "total_score": 5,
                "week_score": 3,
                "current_streak": 3,
                "best_streak": 3,
                "last_correct_date": FROZEN_TODAY,
                "last_answered_date": FROZEN_TODAY,
                "first_name": "Test",
            }
        )
        # Must not raise
        repo.update_score_correct("chat1", "user1", "Test")
        mock_table.update_item.assert_called_once()


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
        repo.update_score_wrong("chat1", "user1", "Test")

        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]
        vals = call_kwargs["ExpressionAttributeValues"]
        assert vals[":zero"] == 0
        assert vals[":today"] == FROZEN_TODAY
        # streak reset is expressed via :zero in the UpdateExpression
        assert "current_streak = :zero" in call_kwargs["UpdateExpression"]

    @_PATCH_YESTERDAY
    @_PATCH_TODAY
    @patch("services.repositories.quiz.get_dynamodb")
    def test_duplicate_wrong_same_day_is_noop(self, mock_dynamo, _m_today, _m_yday):
        """DynamoDB ConditionExpression blocks the duplicate; the method must swallow it."""
        mock_table = MagicMock()
        mock_dynamo.return_value.Table.return_value = mock_table
        mock_table.update_item.side_effect = _conditional_check_failed()

        from services.repositories.quiz import QuizRepository

        repo = QuizRepository()
        # Must not raise
        repo.update_score_wrong("chat1", "user1", "Test")
        mock_table.update_item.assert_called_once()
