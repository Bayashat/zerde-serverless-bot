"""Product outcomes under failed, repeated, concurrent and stale moderation work."""

import importlib
import json
from unittest.mock import MagicMock

import pytest
from core.dispatcher import Context
from services.handlers.spam_review import handle_spam_review_callback
from services.repositories.spam import SpamLeaseBusyError
from services.spam.enforcer import SpamEnforcer
from services.spam.groq_detector import SpamCheckResult
from services.spam.processor import process_spam_check_task
from services.telegram import TelegramAPIError, TelegramClient

from tests import spam_fakes


def _body(version=1):
    return {
        "chat_id": -1001,
        "user_id": 42,
        "message_id": 10,
        "text": "synthetic private current message",
        "triggered_rules": ["external_mention"],
        "source_ref": {"source_id": "10", "source_version": version, "epoch": "new-chat-epoch"},
    }


def _bot():
    bot = MagicMock()
    bot.get_chat_member.return_value = {"status": "member"}
    bot.send_message.return_value = {"message_id": 99}
    return bot


def _classifier(monkeypatch, label="NOT_SPAM", confidence=0.99, *, error=False):
    detector = MagicMock()
    detector.classify.return_value = SpamCheckResult(label, confidence, "not_spam", error=error)
    monkeypatch.setattr("services.spam.processor._get_detector", lambda: detector)
    return detector


def _callback(case_id, *, action="ban", chat_id=-1001):
    return Context(
        {
            "callback_query": {
                "id": "callback",
                "data": f"spam_{action}:" + case_id.removeprefix("decision#"),
                "from": {"id": 7},
                "message": {"message_id": 99, "chat": {"id": chat_id, "type": "supergroup"}},
            }
        },
        _bot(),
    )


@pytest.mark.parametrize("error", [TelegramAPIError(429, "rate limited"), TimeoutError("timed out")])
def test_transient_ban_failure_retries_without_a_success_counter(spam_repo, error):
    bot = _bot()
    bot.kick_chat_member.side_effect = error
    with pytest.raises(type(error)):
        SpamEnforcer(bot).enforce(-1001, 42, 10, "spam")
    assert spam_repo.ban_count == 0
    assert not any(row["state"] == "banned" for row in spam_repo.rows.values())


def test_permission_failure_is_a_durable_failure_not_a_ban(spam_repo):
    bot = _bot()
    bot.ban_chat_member.side_effect = TelegramAPIError(403, "not enough rights")
    result = SpamEnforcer(bot).enforce(-1001, 42, 10, "review", permanent=True)
    assert result.state == "failed"
    assert result.reason == "telegram_http_403"
    assert spam_repo.ban_count == 0


def test_partial_success_resumes_without_redeleting_or_extending_the_ban(monkeypatch, spam_repo):
    monkeypatch.setattr("services.spam.enforcer.time.time", lambda: 1000)
    bot = _bot()
    bot.kick_chat_member.side_effect = [TimeoutError("retry"), None]
    enforcer = SpamEnforcer(bot)
    with pytest.raises(TimeoutError):
        enforcer.enforce(-1001, 42, 10, "spam")
    monkeypatch.setattr("services.spam.enforcer.time.time", lambda: 1001)
    assert enforcer.enforce(-1001, 42, 10, "spam").banned
    assert enforcer.enforce(-1001, 42, 10, "spam").banned
    assert bot.delete_message.call_count == 1
    assert [call.kwargs["until_date"] for call in bot.kick_chat_member.call_args_list] == [1060, 1060]
    assert spam_repo.ban_count == 1


def test_retry_near_expiry_never_becomes_a_permanent_ban(monkeypatch, spam_repo):
    monkeypatch.setattr("services.spam.enforcer.time.time", lambda: 1000)
    bot = _bot()
    bot.kick_chat_member.side_effect = TimeoutError("retry")
    enforcer = SpamEnforcer(bot)
    with pytest.raises(TimeoutError):
        enforcer.enforce(-1001, 42, 10, "spam")
    monkeypatch.setattr("services.spam.enforcer.time.time", lambda: 1021)
    assert enforcer.enforce(-1001, 42, 10, "spam").state == "failed"
    assert bot.kick_chat_member.call_count == 1
    bot.ban_chat_member.assert_not_called()
    assert spam_repo.ban_count == 0


def test_old_31_second_config_gets_safe_60_seconds_at_first_ban_attempt(monkeypatch, spam_repo):
    monkeypatch.setattr("services.spam.enforcer.KICK_BAN_DURATION_SECONDS", 31)
    monkeypatch.setattr("services.spam.enforcer.KICK_BAN_CONFIGURED_DURATION_SECONDS", 31)
    now = [1000]
    monkeypatch.setattr("services.spam.enforcer.time.time", lambda: now[0])
    bot = _bot()
    bot.delete_message.side_effect = lambda *args, **kwargs: now.__setitem__(0, 1015)
    assert SpamEnforcer(bot).enforce(-1001, 42, 10, "spam").banned
    assert bot.kick_chat_member.call_args.kwargs["until_date"] == 1075
    assert spam_repo.ban_count == 1


@pytest.mark.parametrize("raw_duration", ["31", None])
def test_runtime_config_normalizes_legacy_short_duration_and_defaults_to_60(monkeypatch, raw_duration):
    from core import config

    try:
        with monkeypatch.context() as patch:
            if raw_duration is None:
                patch.delenv("KICK_BAN_DURATION_SECONDS", raising=False)
            else:
                patch.setenv("KICK_BAN_DURATION_SECONDS", raw_duration)
            importlib.reload(config)
            assert config.KICK_BAN_DURATION_SECONDS == 60
    finally:
        importlib.reload(config)


def test_unknown_membership_never_grants_enforcement_permission(spam_repo):
    bot = _bot()
    bot.get_chat_member.side_effect = TimeoutError("membership unavailable")
    with pytest.raises(TimeoutError):
        SpamEnforcer(bot).enforce(-1001, 42, 10, "spam")
    bot.delete_message.assert_not_called()
    assert spam_repo.ban_count == 0


def test_already_banned_target_does_not_claim_someone_elses_counter(spam_repo):
    bot = _bot()
    bot.get_chat_member.return_value = {"status": "kicked", "until_date": 0}
    assert SpamEnforcer(bot).enforce(-1001, 42, 10, "spam").reason == "already_banned"
    bot.kick_chat_member.assert_not_called()
    assert spam_repo.ban_count == 0


def test_clean_receipt_survives_replay_and_references_exact_source_version(monkeypatch, spam_repo):
    detector = _classifier(monkeypatch)
    bot = _bot()
    assert process_spam_check_task(bot, _body()) == "clean"
    assert process_spam_check_task(bot, _body()) == "clean"
    assert detector.classify.call_count == 1
    receipt = next(iter(spam_repo.rows.values()))
    assert receipt["source_ref"] == _body()["source_ref"]
    assert receipt["outbox_pending"] is True
    assert "ttl" not in receipt
    assert _body()["text"] not in json.dumps(receipt)
    assert process_spam_check_task(bot, _body(version=2)) == "clean"
    assert len(spam_repo.rows) == 2
    assert detector.classify.call_count == 2


def test_provider_failure_never_creates_clean_receipt(monkeypatch, spam_repo):
    _classifier(monkeypatch, error=True)
    with pytest.raises(Exception, match="spam classifier failed"):
        process_spam_check_task(_bot(), _body())
    assert all(row["state"] == "pending" and not row.get("outbox_pending") for row in spam_repo.rows.values())


def test_administrator_exemption_still_finishes_versioned_quarantined_source(monkeypatch, spam_repo):
    detector = _classifier(monkeypatch)
    bot = _bot()
    bot.get_chat_member.return_value = {"status": "administrator"}
    assert process_spam_check_task(bot, _body()) == "clean"
    detector.classify.assert_not_called()
    case = next(iter(spam_repo.rows.values()))
    assert case["reason"] == "administrator_exempt"
    assert case["outbox_pending"] and "ttl" not in case


def test_captcha_read_failure_preserves_quarantine(monkeypatch, spam_repo):
    detector = _classifier(monkeypatch)
    captcha = MagicMock()
    captcha.get_pending.side_effect = RuntimeError("DynamoDB read failed")
    with pytest.raises(RuntimeError):
        process_spam_check_task(_bot(), _body(), captcha_repo=captcha)
    detector.classify.assert_not_called()
    assert not spam_repo.rows


def test_review_delivery_failure_recovers_without_classifying_or_sending_twice(monkeypatch, spam_repo):
    detector = _classifier(monkeypatch, "SPAM", 0.7)
    bot = _bot()
    bot.send_message.side_effect = [TimeoutError("delivery failed"), {"message_id": 99}]
    with pytest.raises(TimeoutError):
        process_spam_check_task(bot, _body())
    assert process_spam_check_task(bot, _body()) == "review"
    assert process_spam_check_task(bot, _body()) == "review"
    assert detector.classify.call_count == 1
    assert bot.send_message.call_count == 2


def test_admin_ignore_has_durable_clean_outcome_and_cannot_later_ban(monkeypatch, spam_repo):
    _classifier(monkeypatch, "SPAM", 0.7)
    process_spam_check_task(_bot(), _body())
    case_id = next(iter(spam_repo.rows))
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda ctx: True)
    ctx = _callback(case_id, action="ignore")
    handle_spam_review_callback(ctx)
    row = spam_repo.get(case_id)
    assert row["state"] == "clean" and row["outbox_pending"] and "ttl" not in row
    ban_ctx = _callback(case_id)
    handle_spam_review_callback(ban_ctx)
    ban_ctx.bot.ban_chat_member.assert_not_called()
    assert spam_repo.ban_count == 0


def test_admin_ban_failure_keeps_buttons_and_retry_only_counts_confirmed_success(monkeypatch, spam_repo):
    _classifier(monkeypatch, "SPAM", 0.7)
    process_spam_check_task(_bot(), _body())
    case_id = next(iter(spam_repo.rows))
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda ctx: True)
    ctx = _callback(case_id)
    ctx.bot.ban_chat_member.side_effect = [TelegramAPIError(403, "missing rights"), None]
    handle_spam_review_callback(ctx)
    ctx.bot.edit_message_text.assert_not_called()
    assert ctx.bot.answer_callback_query.call_args.kwargs["show_alert"] is True
    assert spam_repo.ban_count == 0
    handle_spam_review_callback(ctx)
    handle_spam_review_callback(ctx)
    assert ctx.bot.ban_chat_member.call_count == 2
    assert spam_repo.ban_count == 1
    assert spam_repo.get(case_id)["state"] == "blocked"


def test_ban_success_then_terminal_write_failure_cannot_be_ignored_into_clean(monkeypatch, spam_repo):
    _classifier(monkeypatch, "SPAM", 0.7)
    process_spam_check_task(_bot(), _body())
    case_id = next(iter(spam_repo.rows))
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda ctx: True)
    original_update = spam_repo.update

    def fail_terminal_write(case_id, owner, fields, **kwargs):
        if fields.get("state") == "blocked":
            raise RuntimeError("decision write unavailable")
        return original_update(case_id, owner, fields, **kwargs)

    monkeypatch.setattr(spam_repo, "update", fail_terminal_write)
    ban_ctx = _callback(case_id)
    handle_spam_review_callback(ban_ctx)
    assert spam_repo.ban_count == 1
    assert spam_repo.get(case_id)["state"] == "review"
    assert spam_repo.get(case_id)["selected_action"] == "ban"
    # Alert delivery can succeed before its marker write. Worker recovery still
    # must respect the durable ban intent even if the actor is now exempt.
    spam_repo.rows[case_id]["alert_sent"] = False
    promoted_bot = _bot()
    promoted_bot.get_chat_member.return_value = {"status": "administrator"}
    assert process_spam_check_task(promoted_bot, _body()) == "review"
    ignore_ctx = _callback(case_id, action="ignore")
    handle_spam_review_callback(ignore_ctx)
    assert spam_repo.get(case_id)["state"] != "clean"
    assert not spam_repo.get(case_id).get("outbox_pending")
    monkeypatch.setattr(spam_repo, "update", original_update)
    handle_spam_review_callback(ban_ctx)
    assert spam_repo.ban_count == 1
    assert ban_ctx.bot.ban_chat_member.call_count == 1
    assert spam_repo.get(case_id)["state"] == "blocked"


def test_parallel_worker_retries_and_cross_chat_callback_cannot_act(monkeypatch, spam_repo):
    detector = _classifier(monkeypatch)
    case = spam_repo.ensure_case(_body())
    spam_repo.claim(case["case_id"])
    with pytest.raises(SpamLeaseBusyError):
        process_spam_check_task(_bot(), _body())
    detector.classify.assert_not_called()
    monkeypatch.setattr("services.handlers.spam_review._is_admin", lambda ctx: True)
    ctx = _callback(case["case_id"], chat_id=-1002)
    handle_spam_review_callback(ctx)
    ctx.bot.ban_chat_member.assert_not_called()
    assert spam_repo.ban_count == 0


@pytest.mark.parametrize("method", ["ban_chat_member", "kick_chat_member", "delete_message"])
def test_actual_telegram_client_requires_positive_moderation_acknowledgement(method):
    bot = TelegramClient()
    bot._post = MagicMock(return_value={"ok": True, "result": False})
    with pytest.raises(RuntimeError, match="success was not confirmed"):
        getattr(bot, method)(-1001, 42)


spam_repo = spam_fakes.spam_repo
