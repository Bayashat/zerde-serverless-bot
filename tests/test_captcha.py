"""Captcha fault/concurrency contracts against Moto's DynamoDB emulator.

These tests exercise real repository condition expressions, not live AWS.
Telegram effects are simulated separately so ambiguous delivery can be injected.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from core.dispatcher import Context
from moto import mock_aws
from services.handlers import captcha
from services.repositories import captcha as repository
from services.repositories.captcha import CaptchaBusyError, CaptchaRepository, CaptchaRetryRequiredError
from services.repositories.sqs import SQSClient

CHAT, USER, JOIN, VERIFY = -100123, 42, 5, 6


def dependency_error():
    return ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "synthetic"}}, "GetItem")


@pytest.fixture
def env(monkeypatch):
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
        table = dynamodb.create_table(
            TableName="test-stats-table",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(repository, "get_dynamodb", lambda: dynamodb)
        clock = SimpleNamespace(now=2_000_000_000)
        timer = SimpleNamespace(time=lambda: clock.now)
        monkeypatch.setattr(repository, "time", timer)
        monkeypatch.setattr(captcha, "time", timer)
        monkeypatch.setattr(captcha, "generate_grid_captcha", lambda: (b"synthetic-captcha", "3719"))
        state = {"status": "member"}
        bot = MagicMock()
        bot.get_chat_member.side_effect = lambda *_: dict(state)

        def restrict(_chat, _user, permissions):
            state.clear()
            state.update({"status": "restricted", **permissions})
            if permissions == captcha._FULL_PERMISSIONS:
                state["status"] = "member"

        def kick(*_):
            state.clear()
            state["status"] = "kicked"

        bot.restrict_chat_member.side_effect = restrict
        bot.kick_chat_member.side_effect = kick
        bot.send_photo.return_value = {"message_id": VERIFY}
        bot.send_message.return_value = {"message_id": 900}
        yield SimpleNamespace(repo=CaptchaRepository(), table=table, clock=clock, bot=bot, state=state, sqs=MagicMock())


def context(env, *, text="3719", message_id=10, join=False, user=USER):
    message = {
        "message_id": message_id,
        "text": text,
        "chat": {"id": CHAT, "type": "supergroup"},
        "from": {"id": user, "first_name": "Synthetic"},
    }
    if join:
        message["new_chat_members"] = [{"id": user, "first_name": "Synthetic", "is_bot": False}]
    return Context({"message": message}, env.bot, captcha_repo=env.repo, sqs_repo=env.sqs, stats_repo=MagicMock())


def start(env, join=JOIN):
    captcha.handle_new_member(context(env, message_id=join, join=True))
    return env.repo.get_challenge(CHAT, USER)


def task(env, challenge=None, *, legacy=False):
    c = challenge or env.repo.get_challenge(CHAT, USER)
    result = {
        "chat_id": CHAT,
        "user_id": USER,
        "join_message_id": int(c["join_msg_id"]),
        "verification_message_id": int(c.get("verify_msg_id", 0)),
        "_captcha_repo": env.repo,
        "_sqs_repo": env.sqs,
    }
    if not legacy:
        result["generation"] = c["generation"]
    return result


def timeout(env, payload=None):
    env.clock.now += repository.CAPTCHA_LEASE_SECONDS + captcha.CAPTCHA_TIMEOUT_SECONDS
    captcha.process_timeout_task(env.bot, payload or task(env))


def test_creation_persists_and_enqueues_before_restriction(env):
    real_restrict = env.bot.restrict_chat_member.side_effect

    def assert_ready(*args):
        assert env.repo.get_challenge(CHAT, USER)["status"] == "creating"
        env.sqs.send_timeout_task.assert_called_once()
        real_restrict(*args)

    env.bot.restrict_chat_member.side_effect = assert_ready
    result = start(env)
    assert result["status"] == "pending"
    assert result["generation"]
    assert result["verify_msg_id"] == VERIFY
    assert env.sqs.send_timeout_task.call_args.kwargs["generation"] == result["generation"]


def test_correct_answer_decides_before_unrestrict_and_timeout_never_kicks(env):
    start(env)
    real_restrict = env.bot.restrict_chat_member.side_effect

    def verify_decision(*args):
        assert env.repo.get_challenge(CHAT, USER)["status"] == "verified"
        real_restrict(*args)

    env.bot.restrict_chat_member.side_effect = verify_decision
    captcha.handle_captcha_answer(context(env))
    saved = env.repo.get_challenge(CHAT, USER)
    assert saved["action_done"] is True
    assert env.repo.get_pending(CHAT, USER) is None
    timeout(env)
    env.bot.kick_chat_member.assert_not_called()
    assert env.repo.get_challenge(CHAT, USER)["generation"] == saved["generation"]


def test_decision_write_failure_does_not_unrestrict_or_ack_answer(env, monkeypatch):
    start(env)
    real_save = env.repo.save

    def save(challenge, **changes):
        if changes.get("status") == "verified":
            raise dependency_error()
        return real_save(challenge, **changes)

    monkeypatch.setattr(env.repo, "save", save)
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env))
    assert env.state["status"] == "restricted"
    assert env.repo.get_challenge(CHAT, USER)["status"] == "pending"
    monkeypatch.setattr(env.repo, "save", real_save)
    captcha.handle_captcha_answer(context(env))
    timeout(env)
    env.bot.kick_chat_member.assert_not_called()


def test_lost_verified_write_response_recovers_without_kick(env, monkeypatch):
    start(env)
    real_save = env.repo.save
    lost = False

    def save(challenge, **changes):
        nonlocal lost
        result = real_save(challenge, **changes)
        if changes.get("status") == "verified" and not lost:
            lost = True
            raise ConnectionError("synthetic response loss")
        return result

    monkeypatch.setattr(env.repo, "save", save)
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env))
    assert env.repo.get_challenge(CHAT, USER)["status"] == "verified"
    timeout(env)
    assert env.state["status"] == "member"
    env.bot.kick_chat_member.assert_not_called()


def test_unrestrict_failure_keeps_durable_verified_and_timeout_retries(env):
    start(env)
    restore = env.bot.restrict_chat_member.side_effect
    env.bot.restrict_chat_member.side_effect = ConnectionError("synthetic transport failure")
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env))
    assert env.repo.get_challenge(CHAT, USER)["status"] == "verified"
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is False
    env.bot.restrict_chat_member.side_effect = restore
    timeout(env)
    assert env.state["status"] == "member"
    env.bot.kick_chat_member.assert_not_called()


def test_ambiguous_unrestrict_is_reconciled_without_repeating_effect(env):
    start(env)
    real_restrict = env.bot.restrict_chat_member.side_effect

    def lost_response(*args):
        real_restrict(*args)
        raise ConnectionError("synthetic response loss")

    env.bot.restrict_chat_member.side_effect = lost_response
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env))
    attempts = env.bot.restrict_chat_member.call_count
    timeout(env)
    assert env.bot.restrict_chat_member.call_count == attempts
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is True


def test_correct_and_timeout_compete_for_one_lease_and_decision(env):
    start(env)
    snapshot = env.repo.get_challenge(CHAT, USER)
    verifier = env.repo.acquire(snapshot)
    with pytest.raises(CaptchaBusyError):
        env.repo.acquire(snapshot)
    verified = env.repo.save(verifier, status="verified", decided_at=env.clock.now)
    env.repo.release(verified)
    with pytest.raises(CaptchaBusyError):
        env.repo.acquire(snapshot)
    timeout(env)
    env.bot.kick_chat_member.assert_not_called()
    assert env.repo.get_challenge(CHAT, USER)["status"] == "verified"


def test_expired_lease_cannot_overwrite_winning_timeout_decision(env):
    start(env)
    stale = env.repo.acquire(env.repo.get_challenge(CHAT, USER))
    timeout(env)
    with pytest.raises(CaptchaBusyError):
        env.repo.save(stale, status="verified")
    assert env.repo.get_challenge(CHAT, USER)["status"] == "rejected"
    assert env.state["status"] == "kicked"


def test_timeout_decision_is_immutable(env):
    start(env)
    timeout(env)
    owned = env.repo.acquire(env.repo.get_challenge(CHAT, USER))
    with pytest.raises(ValueError, match="immutable"):
        env.repo.save(owned, status="verified")
    env.repo.release(owned)


def test_kick_failure_remains_recoverable_without_deleting_state(env):
    start(env)
    kick = env.bot.kick_chat_member.side_effect
    env.bot.kick_chat_member.side_effect = ConnectionError("synthetic failure")
    with pytest.raises(ConnectionError):
        timeout(env)
    assert env.repo.get_challenge(CHAT, USER)["status"] == "rejected"
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is False
    env.bot.kick_chat_member.side_effect = kick
    captcha.process_timeout_task(env.bot, task(env))
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is True


def test_kick_response_loss_does_not_extend_ban_on_retry(env):
    start(env)
    kick = env.bot.kick_chat_member.side_effect

    def lost(*args):
        kick(*args)
        raise ConnectionError("synthetic response loss")

    env.bot.kick_chat_member.side_effect = lost
    with pytest.raises(ConnectionError):
        timeout(env)
    captcha.process_timeout_task(env.bot, task(env))
    env.bot.kick_chat_member.assert_called_once()
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is True


def test_rejoin_cannot_replace_generation_while_old_action_lease_active(env):
    start(env)
    old = env.repo.acquire(env.repo.get_challenge(CHAT, USER))
    with pytest.raises(CaptchaRetryRequiredError):
        start(env, join=JOIN + 10)
    assert env.repo.get_challenge(CHAT, USER)["generation"] == old["generation"]
    env.repo.release(old)
    newer = start(env, join=JOIN + 10)
    assert newer["generation"] != old["generation"]
    with pytest.raises(CaptchaBusyError):
        env.repo.assert_owned(old)


def test_old_timeout_and_old_join_replay_cannot_harm_new_challenge(env):
    old = start(env)
    newer = start(env, join=JOIN + 10)
    captcha.process_timeout_task(env.bot, task(env, old))
    captcha.process_timeout_task(env.bot, task(env, old, legacy=True))
    start(env, join=JOIN)
    assert env.repo.get_challenge(CHAT, USER)["generation"] == newer["generation"]
    env.bot.kick_chat_member.assert_not_called()
    assert env.bot.send_photo.call_count == 2


def test_same_join_replay_does_not_reset_answer_or_send_another_captcha(env):
    first = start(env)
    again = start(env)
    assert again == first
    env.bot.send_photo.assert_called_once()


def test_queue_failure_happens_before_any_restriction_and_retry_recovers(env):
    env.sqs.send_timeout_task.side_effect = ConnectionError("synthetic enqueue failure")
    with pytest.raises(CaptchaRetryRequiredError):
        start(env)
    env.bot.restrict_chat_member.assert_not_called()
    env.bot.send_photo.assert_not_called()
    assert env.repo.get_challenge(CHAT, USER)["status"] == "preparing"
    env.sqs.send_timeout_task.side_effect = None
    assert start(env)["status"] == "pending"


def test_prepare_failure_happens_before_any_telegram_effect(env, monkeypatch):
    monkeypatch.setattr(env.repo, "prepare", MagicMock(side_effect=dependency_error()))
    with pytest.raises(CaptchaRetryRequiredError):
        start(env)
    env.bot.restrict_chat_member.assert_not_called()
    env.sqs.send_timeout_task.assert_not_called()


@pytest.mark.parametrize("failure_stage", ["restriction", "photo", "invalid_photo_response"])
def test_creation_failure_cancels_and_restores_instead_of_kicking(env, failure_stage):
    if failure_stage == "restriction":
        env.bot.restrict_chat_member.side_effect = ConnectionError("synthetic restrict failure")
    elif failure_stage == "photo":
        env.bot.send_photo.side_effect = ConnectionError("synthetic send failure")
    else:
        env.bot.send_photo.return_value = {}
    start(env)
    assert env.repo.get_challenge(CHAT, USER)["status"] == "cancelled"
    assert env.state["status"] == "member"
    timeout(env)
    env.bot.kick_chat_member.assert_not_called()


def test_crash_after_restriction_before_activation_is_recovered_as_cancelled(env):
    c = env.repo.prepare(CHAT, USER, JOIN)
    c = env.repo.acquire(c)
    c = env.repo.save(c, status="creating", expected="3719")
    env.bot.restrict_chat_member(CHAT, USER, captcha._TEXT_ONLY_PERMISSIONS)
    # Simulate process death: no lease release and no activation.
    timeout(env, task(env, c))
    assert env.repo.get_challenge(CHAT, USER)["status"] == "cancelled"
    assert env.state["status"] == "member"
    env.bot.kick_chat_member.assert_not_called()


def test_live_creation_lease_reschedules_recovery_without_effect(env):
    c = env.repo.prepare(CHAT, USER, JOIN)
    c = env.repo.acquire(c)
    captcha.process_timeout_task(env.bot, task(env, c))
    env.sqs.send_timeout_task.assert_called_once()
    env.bot.get_chat_member.assert_not_called()


def test_early_timeout_reschedules_until_persisted_deadline(env):
    start(env)
    env.sqs.reset_mock()
    captcha.process_timeout_task(env.bot, task(env))
    env.sqs.send_timeout_task.assert_called_once()
    assert env.repo.get_challenge(CHAT, USER)["status"] == "pending"
    env.bot.kick_chat_member.assert_not_called()


def test_read_failure_is_not_missing_and_timeout_never_deletes_state(env, monkeypatch):
    start(env)
    original = env.repo.get_challenge
    monkeypatch.setattr(env.repo, "get_challenge", MagicMock(side_effect=dependency_error()))
    with pytest.raises(ClientError):
        captcha.process_timeout_task(env.bot, task(env, {"generation": "synthetic", "join_msg_id": JOIN}))
    monkeypatch.setattr(env.repo, "get_challenge", original)
    assert env.repo.get_challenge(CHAT, USER)["status"] == "pending"
    env.bot.kick_chat_member.assert_not_called()


def test_repository_read_dependency_error_propagates(env, monkeypatch):
    table = MagicMock()
    table.get_item.side_effect = dependency_error()
    dynamodb = MagicMock()
    dynamodb.Table.return_value = table
    monkeypatch.setattr(repository, "get_dynamodb", lambda: dynamodb)
    with pytest.raises(ClientError):
        env.repo.get_challenge(CHAT, USER)


def test_wrong_attempt_replay_counts_once_and_threshold_decides_before_kick(env):
    start(env)
    ctx = context(env, text="not an answer", message_id=10)
    captcha.handle_captcha_answer(ctx)
    captcha.handle_captcha_answer(ctx)
    assert env.repo.get_challenge(CHAT, USER)["attempts"] == 1
    for i in range(1, captcha.CAPTCHA_MAX_ATTEMPTS):
        captcha.handle_captcha_answer(context(env, text="0000", message_id=10 + i))
    saved = env.repo.get_challenge(CHAT, USER)
    assert saved["status"] == "rejected"
    assert saved["decision_reason"] == "wrong_attempts"
    assert saved["attempts"] == captcha.CAPTCHA_MAX_ATTEMPTS
    assert saved["action_done"] is True
    env.bot.kick_chat_member.assert_called_once()


def test_expired_pending_still_routes_to_captcha(env):
    start(env)
    env.clock.now += captcha.CAPTCHA_TIMEOUT_SECONDS
    assert env.repo.get_pending(CHAT, USER)
    captcha.handle_captcha_answer(context(env))
    assert env.repo.get_challenge(CHAT, USER)["status"] == "rejected"


def test_admin_changed_permissions_are_not_overridden(env):
    start(env)
    env.state["can_send_messages"] = False
    captcha.handle_captcha_answer(context(env))
    assert env.state["can_send_messages"] is False
    assert env.bot.restrict_chat_member.call_count == 1


def test_missing_state_does_not_touch_member_or_delete_new_state(env):
    captcha.process_timeout_task(env.bot, task(env, {"generation": "missing", "join_msg_id": JOIN}))
    env.bot.get_chat_member.assert_not_called()
    assert env.table.scan()["Count"] == 0


def test_no_repository_never_kicks_based_only_on_current_permissions(env):
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.process_timeout_task(env.bot, {"chat_id": CHAT, "user_id": USER, "join_message_id": JOIN})
    env.bot.get_chat_member.assert_not_called()


@pytest.mark.parametrize("status", ["pending", "verified"])
def test_legacy_timeout_requires_exact_anchors_and_migrates_safely(env, status):
    env.table.put_item(
        Item={
            "stat_key": f"captcha_pending#{CHAT}#{USER}",
            "status": status,
            "expected": "3719",
            "join_msg_id": JOIN,
            "verify_msg_id": VERIFY,
            "expires_at": env.clock.now - 1,
            "ttl": env.clock.now + 100,
        }
    )
    env.state.update({"status": "restricted", **captcha._TEXT_ONLY_PERMISSIONS})
    payload = task(env, legacy=True)
    mismatched = {**payload, "verification_message_id": VERIFY + 1}
    captcha.process_timeout_task(env.bot, mismatched)
    env.bot.kick_chat_member.assert_not_called()
    captcha.process_timeout_task(env.bot, payload)
    if status == "pending":
        env.bot.kick_chat_member.assert_called_once()
        assert env.repo.get_challenge(CHAT, USER)["generation"]
    else:
        env.bot.kick_chat_member.assert_not_called()


def test_sqs_timeout_payload_is_generation_scoped_and_delay_is_bounded():
    transport = MagicMock()
    with patch("services.repositories.sqs._get_sqs_client", return_value=transport):
        SQSClient().send_timeout_task(CHAT, USER, JOIN, 0, delay_seconds=2000, generation="new-generation")
    kwargs = transport.send_message.call_args.kwargs
    assert kwargs["DelaySeconds"] == 900
    assert json.loads(kwargs["MessageBody"])["generation"] == "new-generation"


def test_invalid_telegram_readback_does_not_mark_action_complete(env):
    start(env)
    env.bot.get_chat_member.side_effect = lambda *_: {}
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env))
    assert env.repo.get_challenge(CHAT, USER)["status"] == "verified"
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is False


def test_activation_write_failure_restores_member_and_keeps_recovery_task(env, monkeypatch):
    real_save = env.repo.save

    def save(challenge, **changes):
        if changes.get("status") == "pending":
            raise dependency_error()
        return real_save(challenge, **changes)

    monkeypatch.setattr(env.repo, "save", save)
    result = start(env)
    assert result["status"] == "cancelled"
    assert result["action_done"] is True
    assert env.state["status"] == "member"
    env.sqs.send_timeout_task.assert_called_once()
    timeout(env)
    env.bot.kick_chat_member.assert_not_called()


def test_lost_activation_write_response_keeps_confirmed_pending(env, monkeypatch):
    real_save = env.repo.save

    def save(challenge, **changes):
        result = real_save(challenge, **changes)
        if changes.get("status") == "pending":
            raise ConnectionError("synthetic response loss")
        return result

    monkeypatch.setattr(env.repo, "save", save)
    result = start(env)
    assert result["status"] == "pending"
    assert env.state["status"] == "restricted"
    env.bot.send_photo.assert_called_once()


def test_completed_state_write_failure_recovers_without_repeating_kick(env, monkeypatch):
    start(env)
    real_save = env.repo.save

    def save(challenge, **changes):
        if changes.get("action_done"):
            raise dependency_error()
        return real_save(challenge, **changes)

    monkeypatch.setattr(env.repo, "save", save)
    with pytest.raises(ClientError):
        timeout(env)
    assert env.state["status"] == "kicked"
    monkeypatch.setattr(env.repo, "save", real_save)
    captcha.process_timeout_task(env.bot, task(env))
    env.bot.kick_chat_member.assert_called_once()
    assert env.repo.get_challenge(CHAT, USER)["action_done"] is True


def test_webhook_captcha_lookup_failure_returns_500_before_normal_flows(env):
    from webhook import _handle_api_gateway

    dispatcher = MagicMock()
    dispatcher.captcha_repo = env.repo
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(context(env)._update),
    }
    with (
        patch.object(env.repo, "get_pending", side_effect=dependency_error()),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.observe_contest_update") as observe,
        patch("webhook._spam_screening") as screening,
    ):
        response = _handle_api_gateway(event, dispatcher, env.bot)
    assert response["statusCode"] == 500
    observe.assert_not_called()
    screening.return_value.run.assert_not_called()
    dispatcher.process_update.assert_not_called()


def test_webhook_pending_command_cannot_bypass_captcha(env):
    from webhook import _handle_api_gateway

    start(env)
    dispatcher = MagicMock()
    dispatcher.captcha_repo = env.repo
    dispatcher.sqs_repo = env.sqs
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(context(env, text="/ask bypass")._update),
    }
    with patch("webhook.is_configured_group_chat", return_value=True):
        response = _handle_api_gateway(event, dispatcher, env.bot)
    assert response["statusCode"] == 200
    assert env.repo.get_challenge(CHAT, USER)["attempts"] == 1
    dispatcher.process_update.assert_not_called()


def test_webhook_answer_failure_is_retryable(env):
    from webhook import _handle_api_gateway

    start(env)
    dispatcher = MagicMock()
    dispatcher.captcha_repo = env.repo
    dispatcher.sqs_repo = env.sqs
    event = {
        "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
        "body": json.dumps(context(env)._update),
    }
    with (
        patch("webhook.is_configured_group_chat", return_value=True),
        patch.object(env.repo, "save", side_effect=dependency_error()),
    ):
        response = _handle_api_gateway(event, dispatcher, env.bot)
    assert response["statusCode"] == 500
    assert env.state["status"] == "restricted"


def test_new_join_message_is_not_mistaken_for_old_pending_answer(env):
    from webhook import _has_pending_captcha

    start(env)
    dispatcher = MagicMock()
    dispatcher.captcha_repo = env.repo
    assert not _has_pending_captcha(dispatcher, context(env, message_id=JOIN + 10, join=True)._update)


def test_wrong_notice_state_write_failure_is_retryable_without_double_attempt(env, monkeypatch):
    start(env)
    real_save = env.repo.save

    def save(challenge, **changes):
        if 900 in changes.get("wrong_msg_ids", []):
            raise dependency_error()
        return real_save(challenge, **changes)

    monkeypatch.setattr(env.repo, "save", save)
    with pytest.raises(CaptchaRetryRequiredError):
        captcha.handle_captcha_answer(context(env, text="wrong"))
    assert env.repo.get_challenge(CHAT, USER)["attempts"] == 1
    monkeypatch.setattr(env.repo, "save", real_save)
    captcha.handle_captcha_answer(context(env, text="wrong"))
    assert env.repo.get_challenge(CHAT, USER)["attempts"] == 1


@pytest.mark.parametrize("text", ["3719", "wrong"])
@pytest.mark.parametrize("edited", [False, True])
def test_old_answer_and_pre_challenge_messages_never_change_new_generation(env, text, edited):
    from webhook import _handle_api_gateway

    env.bot.send_photo.return_value = {"message_id": 25}
    saved = start(env, join=20)
    env.bot.reset_mock()
    dispatcher = MagicMock()
    dispatcher.captcha_repo = env.repo
    dispatcher.sqs_repo = env.sqs
    for message_id in [10, 11, 12, 20, 21, 25, 10]:
        update = context(env, text=text, message_id=message_id)._update
        if edited:
            update = {"edited_message": update["message"]}
        event = {
            "headers": {"x-telegram-bot-api-secret-token": "test-webhook-secret"},
            "body": json.dumps(update),
        }
        with patch("webhook.is_configured_group_chat", return_value=True):
            assert _handle_api_gateway(event, dispatcher, env.bot)["statusCode"] == 200
    assert env.repo.get_challenge(CHAT, USER) == saved
    env.bot.kick_chat_member.assert_not_called()
    env.bot.restrict_chat_member.assert_not_called()
    env.bot.delete_message.assert_not_called()
    env.bot.send_message.assert_not_called()
    dispatcher.process_update.assert_not_called()
