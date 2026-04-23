"""Tests for the grid image captcha: answer checking, state transitions."""

from unittest.mock import MagicMock


def _make_ctx(text, user_id, chat_id, captcha_repo):
    """Build a minimal Context-like mock for captcha handler tests."""
    from core.dispatcher import Context

    update = {
        "message": {
            "message_id": 10,
            "text": text,
            "chat": {"id": chat_id, "type": "supergroup"},
            "from": {"id": user_id, "first_name": "TestUser", "language_code": "en"},
        }
    }
    bot = MagicMock()
    ctx = Context(update, bot, captcha_repo=captcha_repo)
    return ctx


def test_correct_answer_unrestricts_user():
    """Correct captcha answer → bot.restrict_chat_member with full perms called."""
    from services.handlers.captcha import handle_captcha_answer

    captcha_repo = MagicMock()
    captcha_repo.get_pending.return_value = {
        "expected": "3719",
        "join_msg_id": 5,
        "verify_msg_id": 6,
        "attempts": 0,
    }

    ctx = _make_ctx("3719", user_id=42, chat_id=-100123, captcha_repo=captcha_repo)
    handle_captcha_answer(ctx)

    ctx.bot.restrict_chat_member.assert_called_once()
    captcha_repo.delete_pending.assert_called_once_with(-100123, 42)


def test_wrong_answer_increments_attempts():
    """Wrong answer increments counter and sends error message without kicking."""
    from services.handlers.captcha import handle_captcha_answer

    captcha_repo = MagicMock()
    captcha_repo.get_pending.return_value = {
        "expected": "3719",
        "join_msg_id": 5,
        "verify_msg_id": 6,
        "attempts": 0,
    }
    captcha_repo.increment_attempts.return_value = 1  # 1st wrong attempt

    ctx = _make_ctx("0000", user_id=42, chat_id=-100123, captcha_repo=captcha_repo)
    handle_captcha_answer(ctx)

    captcha_repo.increment_attempts.assert_called_once_with(-100123, 42)
    ctx.bot.kick_chat_member.assert_not_called()
    ctx.bot.restrict_chat_member.assert_not_called()


def test_third_wrong_answer_kicks_user():
    """After CAPTCHA_MAX_ATTEMPTS wrong answers, user is kicked."""
    from core.config import CAPTCHA_MAX_ATTEMPTS
    from services.handlers.captcha import handle_captcha_answer

    captcha_repo = MagicMock()
    captcha_repo.get_pending.return_value = {
        "expected": "3719",
        "join_msg_id": 5,
        "verify_msg_id": 6,
        "attempts": CAPTCHA_MAX_ATTEMPTS - 1,
    }
    captcha_repo.increment_attempts.return_value = CAPTCHA_MAX_ATTEMPTS  # hits limit

    ctx = _make_ctx("0000", user_id=42, chat_id=-100123, captcha_repo=captcha_repo)
    handle_captcha_answer(ctx)

    ctx.bot.kick_chat_member.assert_called_once_with(-100123, 42)
    captcha_repo.delete_pending.assert_called_once()


def test_no_pending_captcha_ignored():
    """Message from user with no pending captcha is silently ignored."""
    from services.handlers.captcha import handle_captcha_answer

    captcha_repo = MagicMock()
    captcha_repo.get_pending.return_value = None

    ctx = _make_ctx("hello", user_id=42, chat_id=-100123, captcha_repo=captcha_repo)
    handle_captcha_answer(ctx)

    ctx.bot.restrict_chat_member.assert_not_called()
    ctx.bot.kick_chat_member.assert_not_called()
