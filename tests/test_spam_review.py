"""Tests for admin review callbacks on low-confidence spam alerts."""

from unittest.mock import MagicMock, patch

from core.dispatcher import Context
from services.handlers.spam_review import handle_spam_review_callback


def _make_ctx(callback_data: str, *, admin_user_id: int = 7) -> Context:
    update = {
        "callback_query": {
            "id": "cb-1",
            "data": callback_data,
            "from": {"id": admin_user_id, "first_name": "Admin"},
            "message": {
                "message_id": 99,
                "chat": {"id": -100123, "type": "supergroup"},
            },
        }
    }
    return Context(update, MagicMock(), stats_repo=MagicMock())


@patch("services.handlers.spam_review.is_chat_admin_or_creator", return_value=False)
def test_spam_review_rejects_non_admin(_mock_is_admin: MagicMock) -> None:
    ctx = _make_ctx("spam_ban:42:10")

    handle_spam_review_callback(ctx)

    ctx.bot.answer_callback_query.assert_called_once()
    assert ctx.bot.answer_callback_query.call_args.kwargs["show_alert"] is True
    ctx.bot.kick_chat_member.assert_not_called()
    ctx.bot.ban_chat_member.assert_not_called()


@patch("services.handlers.spam_review.is_chat_admin_or_creator", return_value=True)
def test_spam_review_ban_enforces_and_replaces_alert(_mock_is_admin: MagicMock) -> None:
    ctx = _make_ctx("spam_ban:42:10")
    ctx.bot.get_chat_member.return_value = {"status": "member", "user": {"username": "spammer"}}

    handle_spam_review_callback(ctx)

    ctx.bot.delete_message.assert_called_once_with(-100123, 10)
    ctx.bot.kick_chat_member.assert_not_called()
    ctx.bot.ban_chat_member.assert_called_once_with(-100123, 42)
    ctx.stats_repo.increment_spam_bans.assert_called_once_with(-100123)
    ctx.bot.edit_message_text.assert_called_once()


@patch("services.handlers.spam_review.is_chat_admin_or_creator", return_value=True)
def test_spam_review_ignore_deletes_alert_without_ban(_mock_is_admin: MagicMock) -> None:
    ctx = _make_ctx("spam_ignore:42:10")

    handle_spam_review_callback(ctx)

    ctx.bot.kick_chat_member.assert_not_called()
    ctx.bot.ban_chat_member.assert_not_called()
    ctx.bot.delete_message.assert_called_once_with(-100123, 99)
    ctx.bot.edit_message_text.assert_not_called()
