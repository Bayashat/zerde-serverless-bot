"""Tests for vote-to-ban finalization cleanup."""

from unittest.mock import MagicMock, call

from services.handlers.voteban import _finalize_ban


def test_finalize_ban_deletes_vote_message_and_target_message_once() -> None:
    ctx = MagicMock()
    ctx.chat_id = -100123
    ctx.message_id = 777
    ctx.stats_repo = MagicMock()
    ctx.vote_repo.get_vote_session.return_value = {
        "reply_message_id": 555,
        "sent_message_id": 777,
        "target_username": "target",
        "target_first_name": "Target",
        "votes_for_info": [{"id": 1, "username": "voter", "first_name": "Voter"}],
    }

    _finalize_ban(ctx, target_user_id=42, votes_for=5)

    ctx.bot.kick_chat_member.assert_called_once_with(-100123, 42)
    ctx.bot.delete_message.assert_has_calls([call(-100123, 777), call(-100123, 555)])
    assert ctx.bot.delete_message.call_count == 2
    ctx.vote_repo.delete_vote_session.assert_called_once_with(-100123, 42)
