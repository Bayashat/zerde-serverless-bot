"""Guest-bot incident regression: delete advertising, review the real caller."""

from unittest.mock import MagicMock, patch

import pytest
from services.spam.groq_detector import SpamCheckResult
from services.spam.message_text import build_spam_context_payload, collect_spam_screen_text
from services.spam.processor import process_spam_check_task
from services.spam.screening_service import SpamScreeningService

CAPTION = (
    "🍃 \u200bД\u200bEᛠርKO€ \u200bᛖОΛΘԿK0 ᛠYᛠ 👇\n" "https://telegra.ph/AKTUALNAYA-SSYLKA-NA-NASHEGO-BOTA-09-10-246\n"
) * 3


def message():
    return {
        "message_id": 42,
        "from": {"id": 900, "is_bot": True},
        "chat": {"id": -100123, "type": "supergroup"},
        "video": {"duration": 4},
        "caption": CAPTION,
        "guest_bot_caller_user": {"id": 111, "is_bot": False},
        "reply_markup": {"inline_keyboard": [[{"text": "СМОТРЕТЬ / ОТКРЫТЬ", "url": "https://example.org/open"}]]},
    }


@pytest.mark.parametrize("key", ["message", "edited_message"])
@patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False)
def test_incident_enters_worker_without_banning_bot_or_caller(admin, key):
    bot, sqs = MagicMock(), MagicMock()
    body = {key: message()}
    service = SpamScreeningService(bot, sqs)
    assert service.should_screen(body)
    assert service.run(body) == "queued"
    payload = sqs.send_spam_check_task.call_args.kwargs
    assert payload["user_id"] == 900
    assert payload["message_context"]["guest_caller_user_id"] == 111
    assert "repeated_obfuscated_url" in payload["triggered_rules"]
    bot.delete_message.assert_not_called()
    bot.ban_chat_member.assert_not_called()


def task(msg):
    return dict(
        chat_id=-100123,
        user_id=900,
        message_id=42,
        text=collect_spam_screen_text(msg),
        triggered_rules=["external_url"],
        message_context=build_spam_context_payload(msg),
    )


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._get_detector")
@patch("services.spam.processor._send_spam_review_alert")
def test_incident_deleted_without_ai_and_caller_reviewed(review, detector, admin):
    bot = MagicMock()
    process_spam_check_task(bot, task(message()))
    bot.delete_message.assert_called_once_with(-100123, 42)
    detector.assert_not_called()
    assert review.call_args.args[2] == 111
    assert review.call_args.kwargs["guest_bot_id"] == 900
    bot.ban_chat_member.assert_not_called()
    bot.kick_chat_member.assert_not_called()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._get_detector")
def test_legitimate_guest_link_is_classified_and_kept(detector, admin):
    msg = message()
    msg["caption"] = "Документация https://github.com/python/cpython"
    detector.return_value.classify.return_value = SpamCheckResult("NOT_SPAM", 0.99, "not_spam")
    bot = MagicMock()
    process_spam_check_task(bot, task(msg))
    detector.return_value.classify.assert_called_once()
    bot.delete_message.assert_not_called()
    bot.send_message.assert_not_called()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._get_detector")
def test_quoted_incident_is_not_deterministically_deleted(detector, admin):
    msg = message()
    msg["caption"] = "Это спам, не открывайте ссылку."
    msg["quote"] = {"text": CAPTION}
    detector.return_value.classify.return_value = SpamCheckResult("NOT_SPAM", 0.99, "not_spam")
    bot = MagicMock()
    process_spam_check_task(bot, task(msg))
    detector.return_value.classify.assert_called_once()
    bot.delete_message.assert_not_called()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._send_spam_review_alert")
def test_missing_personal_caller_never_proposes_bot_ban(review, admin):
    msg = message()
    del msg["guest_bot_caller_user"]
    msg["guest_bot_caller_chat"] = {"id": -222}
    bot = MagicMock()
    process_spam_check_task(bot, task(msg))
    bot.delete_message.assert_called_once()
    review.assert_not_called()
    bot.ban_chat_member.assert_not_called()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._send_spam_review_alert")
def test_guest_delete_failure_retries_without_review(review, admin):
    bot = MagicMock()
    bot.delete_message.side_effect = RuntimeError("Telegram unavailable")
    with pytest.raises(RuntimeError):
        process_spam_check_task(bot, task(message()))
    review.assert_not_called()


def test_hidden_links_and_buttons_are_current_message_only():
    msg = {
        "text": "Открыть",
        "entities": [{"type": "text_link", "url": "https://example.org/a"}],
        "reply_markup": {"inline_keyboard": [[{"text": "Watch", "url": "https://example.org/b"}]]},
        "reply_to_message": {
            "text": "safe",
            "reply_markup": {"inline_keyboard": [[{"text": "spam", "url": "https://example.org/quoted"}]]},
        },
    }
    text = collect_spam_screen_text(msg)
    assert "/a" in text and "/b" in text and "Watch" in text
    assert "/quoted" not in text
    assert build_spam_context_payload(msg)["current_message"] == text


def test_ordinary_bot_still_skipped():
    msg = message()
    del msg["guest_bot_caller_user"]
    assert not SpamScreeningService.should_screen({"message": msg})


@pytest.mark.parametrize(
    "caption",
    [
        "Документация https://example.org/a\n" * 3,
        "\u200bНормальный текст 👩\u200d💻 https://example.org/a",
        "ДE\u200b\u200b\u200bMO https://example.org/a",
    ],
)
def test_normal_unicode_and_repeated_links_do_not_match_incident(caption):
    from services.spam.rule_filter import RuleBasedSpamFilter

    assert "repeated_obfuscated_url" not in RuleBasedSpamFilter().check(caption, 1, -1)[1]


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
def test_guest_review_buttons_target_caller_not_bot(admin):
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member", "user": {"first_name": "User"}}
    process_spam_check_task(bot, task(message()))
    kwargs = bot.send_message.call_args.kwargs
    callbacks = [b["callback_data"] for r in kwargs["reply_markup"]["inline_keyboard"] for b in r]
    assert all(":111:42" in value for value in callbacks)
    assert all(":900:42" not in value for value in callbacks)
    bot.ban_chat_member.assert_not_called()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
@patch("services.spam.processor._send_spam_review_alert")
def test_deleted_message_replay_still_reviews_caller(review, admin):
    bot = MagicMock()
    bot.delete_message.side_effect = RuntimeError("Bad Request: message to delete not found")
    process_spam_check_task(bot, task(message()))
    review.assert_called_once()


@patch("services.spam.processor.is_chat_admin_or_creator", return_value=False)
def test_review_delivery_failure_is_retryable(admin):
    bot = MagicMock()
    bot.send_message.side_effect = RuntimeError("Telegram unavailable")
    with pytest.raises(RuntimeError):
        process_spam_check_task(bot, task(message()))


def test_screening_failure_retries_webhook_and_skips_memory():
    import json

    from webhook import _handle_api_gateway

    dispatcher = MagicMock()
    dispatcher.captcha_repo.get_pending.return_value = None
    screener = MagicMock()
    screener.should_screen.return_value = True
    screener.run.return_value = "error"
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps({"message": message()}),
    }
    with (
        patch("webhook._spam_screening", return_value=screener),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("services.group_memory.observe_update") as observe,
    ):
        result = _handle_api_gateway(event, dispatcher, MagicMock())
    assert result["statusCode"] == 500
    observe.assert_not_called()
    dispatcher.process_update.assert_not_called()
