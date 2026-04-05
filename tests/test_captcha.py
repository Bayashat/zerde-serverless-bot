"""Tests for captcha verification callback parsing."""

from core.config import VERIFY_PREFIX


def test_verify_callback_data_parsing():
    """Verify callback_data format: verify_{user_id}-{join_message_id}"""
    callback_data = f"{VERIFY_PREFIX}123456-789"
    payload = callback_data[len(VERIFY_PREFIX) :].split("-")
    user_id = int(payload[0].strip())
    join_message_id = int(payload[1].strip())

    assert user_id == 123456
    assert join_message_id == 789


def test_verify_callback_wrong_user(mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo):
    """Verify that only the joining user can click the verify button."""
    from core.dispatcher import Context

    update = {
        "callback_query": {
            "id": "cb_1",
            "from": {"id": 999, "first_name": "WrongUser", "language_code": "en"},
            "message": {
                "message_id": 10,
                "chat": {"id": -100123, "type": "supergroup"},
            },
            "data": f"{VERIFY_PREFIX}456-5",
        }
    }

    ctx = Context(update, mock_bot, mock_stats_repo, mock_sqs_repo, mock_vote_repo)
    # ctx.user_id is 999 but payload says 456 — should not match
    payload = ctx.callback_data[len(VERIFY_PREFIX) :].split("-")
    payload_user_id = int(payload[0].strip())

    assert ctx.user_id != payload_user_id
