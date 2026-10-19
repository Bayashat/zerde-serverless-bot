"""Unclassified provider failures stay quarantined across retries and manual review."""

import json
import socket
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from core.dispatcher import Context
from services.handlers.spam_review import handle_spam_review_callback
from services.repositories.spam import GROQ_HTTP_413, SpamLeaseBusyError, classifier_failure_review_target
from services.spam.groq_detector import GroqSpamHTTP413Error
from services.spam.processor import process_spam_check_task
from services.sqs_task_router import process_sqs_event
from zerde_common.ai_errors import ProviderResponseError

from tests import spam_fakes, test_spam_repository_moto


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("This synthetic moderation test must not access the network")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def body(**changes):
    return {
        "task_type": "SPAM_CHECK",
        "chat_id": -1001,
        "user_id": 42,
        "message_id": 10,
        "text": "SYNTHETIC-PRIVATE-INPUT",
        "source_ref": {"source_id": "10", "source_version": 1, "epoch": "epoch"},
        **changes,
    }


def setup_failure(monkeypatch):
    detector = MagicMock()
    detector.classify.side_effect = GroqSpamHTTP413Error("Groq spam API status 413")
    monkeypatch.setattr("services.spam.processor._get_detector", lambda: detector)
    monkeypatch.setattr("services.spam.processor.get_chat_lang", lambda _: "en")
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member"}
    bot.send_message.return_value = {"message_id": 99}
    return detector, bot


def callback(bot, case_id, action="ignore", chat_id=-1001):
    return Context(
        {
            "callback_query": {
                "id": "test",
                "data": f"spam_{action}:" + case_id.removeprefix("decision#"),
                "from": {"id": 7},
                "message": {"message_id": 99, "chat": {"id": chat_id}},
            }
        },
        bot,
    )


def assert_quarantined(row, bot):
    assert row["state"] == "review" and row["classifier_failure"] == GROQ_HTTP_413
    assert not row.get("outbox_pending")
    assert all(key not in row for key in ("decision_label", "confidence_ppm", "selected_action", "lease_owner"))
    assert body()["text"] not in json.dumps(row, default=str)
    bot.delete_message.assert_not_called()
    bot.kick_chat_member.assert_not_called()
    bot.ban_chat_member.assert_not_called()


def test_413_replay_is_neutral_review_and_never_automatic_clean(monkeypatch, spam_repo):
    detector, bot = setup_failure(monkeypatch)
    assert process_spam_check_task(bot, body()) == "review"
    bot.get_chat_member.return_value = {"status": "administrator"}
    assert process_spam_check_task(bot, body()) == "review"
    row = next(iter(spam_repo.rows.values()))
    assert_quarantined(row, bot)
    assert row["provider_review_notice_state"] == "SENT" and row["provider_review_message_id"] == 99
    assert row["alert_sent"] is True and row.get("ttl")
    assert detector.classify.call_count == bot.send_message.call_count == 1
    text = bot.send_message.call_args.args[1]
    assert "could not finish" in text and "%" not in text and body()["text"] not in text
    assert bot.send_message.call_args.kwargs["reply_to_message_id"] == 10
    assert bot.send_message.call_args.kwargs["retries"] is False
    assert bot.send_message.call_args.kwargs["require_confirmation"] is True


@pytest.mark.parametrize(
    "result", [TimeoutError("SYNTHETIC-PRIVATE-ERROR"), {}, {"message_id": True}, {"message_id": 0}]
)
def test_unknown_notice_is_not_resent_or_auto_approved_after_admin_change(monkeypatch, spam_repo, result):
    detector, bot = setup_failure(monkeypatch)
    if isinstance(result, Exception):
        bot.send_message.side_effect = result
    else:
        bot.send_message.return_value = result
    with pytest.raises(ProviderResponseError, match="delivery is unknown"):
        process_spam_check_task(bot, body())
    bot.get_chat_member.return_value = {"status": "administrator"}
    assert process_spam_check_task(bot, body()) == "review"
    row = next(iter(spam_repo.rows.values()))
    assert_quarantined(row, bot)
    assert row["provider_review_notice_state"] == "UNKNOWN" and not row.get("alert_sent")
    assert detector.classify.call_count == bot.send_message.call_count == 1


@pytest.mark.parametrize(
    "field,value", [("classifier_failure", GROQ_HTTP_413), ("provider_review_notice_state", "ATTEMPTED")]
)
def test_failed_pre_effect_write_never_sends_notice(monkeypatch, spam_repo, field, value):
    detector, bot = setup_failure(monkeypatch)
    update = spam_repo.update

    def fail(case_id, owner, fields, **kwargs):
        if fields.get(field) == value:
            raise RuntimeError("synthetic write failure")
        update(case_id, owner, fields, **kwargs)

    monkeypatch.setattr(spam_repo, "update", fail)
    with pytest.raises(RuntimeError):
        process_spam_check_task(bot, body())
    bot.send_message.assert_not_called()
    assert all(not r.get("outbox_pending") and "lease_owner" not in r for r in spam_repo.rows.values())
    monkeypatch.setattr(spam_repo, "update", update)
    assert process_spam_check_task(bot, body()) == "review"
    assert detector.classify.call_count == (2 if field == "classifier_failure" else 1)


@pytest.mark.parametrize("commit_before_error", [False, True])
def test_send_confirmation_write_unknown_does_not_duplicate_notice(monkeypatch, spam_repo, commit_before_error):
    detector, bot = setup_failure(monkeypatch)
    update = spam_repo.update

    def fail(case_id, owner, fields, **kwargs):
        if fields.get("provider_review_notice_state") == "SENT":
            if commit_before_error:
                update(case_id, owner, fields, **kwargs)
            raise RuntimeError("unknown write outcome")
        update(case_id, owner, fields, **kwargs)

    monkeypatch.setattr(spam_repo, "update", fail)
    with pytest.raises(RuntimeError):
        process_spam_check_task(bot, body())
    monkeypatch.setattr(spam_repo, "update", update)
    assert process_spam_check_task(bot, body()) == "review"
    row = next(iter(spam_repo.rows.values()))
    assert_quarantined(row, bot)
    assert row["provider_review_notice_state"] == ("SENT" if commit_before_error else "ATTEMPTED")
    assert detector.classify.call_count == bot.send_message.call_count == 1


@pytest.mark.parametrize("caller", [None, True, 42, -1, 7.5, "7"])
def test_guest_without_valid_personal_caller_has_no_actions_or_callback_fallback(monkeypatch, spam_repo, caller):
    _, bot = setup_failure(monkeypatch)
    message = body(message_context={"guest_bot": True, "guest_caller_user_id": caller})
    assert process_spam_check_task(bot, message) == "review"
    assert bot.send_message.call_args.kwargs["reply_markup"] is None
    case_id = next(iter(spam_repo.rows))
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda _: True)
    for action in ("ban", "ignore"):
        handle_spam_review_callback(callback(bot, case_id, action))
    assert_quarantined(spam_repo.get(case_id), bot)
    assert spam_repo.ban_count == 0


@pytest.mark.parametrize("guest", [False, True])
def test_real_dynamodb_decimal_target_can_be_reviewed_without_model_replay(monkeypatch, actual_repo, guest):
    detector, bot = setup_failure(monkeypatch)
    message = body(message_context={"guest_bot": True, "guest_caller_user_id": 7} if guest else {})
    assert process_spam_check_task(bot, message, moderation_repo=actual_repo) == "review"
    row = actual_repo.ensure_case(message)
    assert isinstance(row["review_target_user_id"], Decimal)
    assert classifier_failure_review_target(row) == (7 if guest else 42)
    assert actual_repo.list_clean_pending()[0] == []
    monkeypatch.setattr("services.handlers.spam_review.SpamRepository", lambda: actual_repo)
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda _: True)
    handle_spam_review_callback(callback(bot, row["case_id"]))
    final = actual_repo.get(row["case_id"])
    assert final["state"] == ("ignored" if guest else "clean")
    assert bool(final.get("outbox_pending")) is (not guest)
    assert detector.classify.call_count == 1
    bot.ban_chat_member.assert_not_called()


@pytest.mark.parametrize("lang", ["en", "kk", "zh", "ru"])
def test_guest_notice_identifies_bot_and_actual_caller_target(monkeypatch, spam_repo, lang):
    _, bot = setup_failure(monkeypatch)
    monkeypatch.setattr("services.spam.processor.get_chat_lang", lambda _: lang)

    def member(chat_id, user_id):
        return {"status": "member", "user": {"first_name": "Bot<&>" if user_id == 42 else "Caller<&>"}}

    bot.get_chat_member.side_effect = member
    assert (
        process_spam_check_task(bot, body(message_context={"guest_bot": True, "guest_caller_user_id": 700123}))
        == "review"
    )
    notice = bot.send_message.call_args.args[1]
    assert '<a href="tg://user?id=42">Bot&lt;&amp;&gt;</a>' in notice
    assert '<a href="tg://user?id=700123">Caller&lt;&amp;&gt;</a>' in notice
    assert "Bot<&>" not in notice and "Caller<&>" not in notice
    assert {"en": "permanently bans", "kk": "біржола бұғаттайды", "zh": "永久封禁", "ru": "бессрочно блокирует"}[
        lang
    ] in notice
    row = next(iter(spam_repo.rows.values()))
    assert classifier_failure_review_target(row) == 700123
    assert bot.send_message.call_args.kwargs["reply_markup"] is not None


@pytest.mark.parametrize("bad", [True, Decimal("1.5"), Decimal("NaN"), Decimal("Infinity"), "7", -1, 0])
def test_invalid_persisted_target_does_not_authorize_callback(bad):
    assert (
        classifier_failure_review_target({"user_id": Decimal(42), "guest_bot": True, "review_target_user_id": bad})
        is None
    )


def test_review_router_does_not_promote_memory_and_new_revision_is_independent(monkeypatch, spam_repo):
    detector, bot = setup_failure(monkeypatch)
    ingestion = MagicMock()
    monkeypatch.setattr("services.sqs_task_router.is_configured_group_chat", lambda _: True)
    event = {"Records": [{"messageId": "synthetic", "body": json.dumps(body())}]}
    for _ in range(2):
        process_sqs_event(event, bot, None, memory_ingestion=ingestion)
    ingestion.promote_clean.assert_not_called()
    assert detector.classify.call_count == 1
    revised = body(source_ref={"source_id": "10", "source_version": 2, "epoch": "epoch"})
    assert process_spam_check_task(bot, revised) == "review"
    assert detector.classify.call_count == 2 and len(spam_repo.rows) == 2


def test_busy_case_cannot_classify_or_send(monkeypatch, spam_repo):
    detector, bot = setup_failure(monkeypatch)
    row = spam_repo.ensure_case(body())
    spam_repo.claim(row["case_id"])
    with pytest.raises(SpamLeaseBusyError):
        process_spam_check_task(bot, body())
    detector.classify.assert_not_called()
    bot.send_message.assert_not_called()


spam_repo = spam_fakes.spam_repo
actual_repo = test_spam_repository_moto.actual_repo
