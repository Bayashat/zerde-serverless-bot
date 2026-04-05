"""Test that poll_answer updates are recognized as relevant by the webhook."""

import os
import sys

os.environ.setdefault("AWS_DEFAULT_REGION", "eu-central-1")
os.environ.setdefault("BOT_TOKEN", "test-bot-token")
os.environ.setdefault("WEBHOOK_SECRET_TOKEN", "test-webhook-secret")
os.environ.setdefault("QUEUE_URL", "https://sqs.eu-central-1.amazonaws.com/123456789/test-queue")
os.environ.setdefault("STATS_TABLE_NAME", "test-stats-table")
os.environ.setdefault("QUIZ_TABLE_NAME", "test-quiz-table")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "bot"))

from webhook import is_event_relevant_to_bot  # noqa: E402


class TestPollAnswerRelevance:
    def test_poll_answer_is_relevant(self):
        body = {
            "update_id": 123,
            "poll_answer": {
                "poll_id": "abc123",
                "user": {"id": 456, "first_name": "Test"},
                "option_ids": [0],
            },
        }
        assert is_event_relevant_to_bot(body) is True

    def test_unrelated_update_still_not_relevant(self):
        body = {"update_id": 123, "edited_message": {"text": "hi"}}
        assert is_event_relevant_to_bot(body) is False
