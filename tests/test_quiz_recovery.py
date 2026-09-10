"""Fault injection on native DynamoDB transactions; no real AWS/Telegram effects."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock
from unittest.mock import Mock

import pytest
from services.quiz_answers import recover_quiz_answers

from tests import quiz_support
from tests.quiz_support import question, sender_module

quiz_env = quiz_support.quiz_env

CHAT = "-100123"


def publish(env, request=1):
    return env.svc.process_on_demand_quiz(CHAT, "en", "python", "medium", request_id=request)


def prepared(env, key="REQUEST#1"):
    execution = env.repo.claim_publication(
        CHAT, key, {"kind": "on_demand", "lang": "en", "topic": "python", "difficulty": "medium", "interactive": False}
    )
    return env.repo.prepare_publication(execution, env.svc._draft(question(), "python", "en", "medium"))


def test_two_daily_invocations_share_one_execution_before_first_send(quiz_env):
    env = quiz_env
    nested = []

    def prepare(*args):
        nested.append(env.svc.process_daily_quiz([CHAT], "ru", scheduled_at=env.clock.now))
        return env.svc._draft(question(), "python", "en", "medium"), []

    env.svc._prepare_daily_publication = prepare
    assert env.svc.process_daily_quiz([CHAT], "en", scheduled_at=env.clock.now)["status"] == "ok"
    assert nested[0]["status"] == "error"
    assert nested[0]["failed"][0]["step"] == "pending"
    assert len(env.sent) == 1


def test_send_intent_is_persisted_before_telegram_and_unknown_is_not_resent(quiz_env):
    env = quiz_env

    def send(**kwargs):
        row = env.repo._publication_read(env.repo.publication_key(CHAT, "REQUEST#1"))
        assert row["state"] == "SENDING"
        env.receipt(**kwargs)  # Fake Telegram accepted, but its response was lost.
        raise sender_module.PollSendUnknown("synthetic lost response")

    env.svc._sender.send_quiz_poll.side_effect = send
    assert publish(env)["status"] == "unknown"
    assert publish(env)["status"] == "unknown"
    assert len(env.sent) == 1
    assert env.repo._publication_read({"PK": "QUIZ_PUBLICATION_OUTBOX", "SK": f"{CHAT}#REQUEST#1"}) == {}


def test_interrupted_sender_becomes_unknown_after_lease(quiz_env):
    env = quiz_env
    execution = env.repo.mark_publication_sending(prepared(env))
    env.clock.now += 331
    assert publish(env)["status"] == "unknown"
    assert env.repo._publication_read({"PK": execution["PK"], "SK": execution["SK"]})["state"] == "UNKNOWN"
    assert not env.sent


def test_known_poll_lookup_survives_final_record_conflict(quiz_env):
    env = quiz_env
    key = "DATE#" + datetime.fromtimestamp(env.clock.now, timezone(timedelta(hours=5))).strftime("%Y-%m-%d")
    execution = env.repo.mark_publication_sending(prepared(env, key))
    message = env.receipt(
        chat_id=CHAT, question=question()["question"], options=question()["options"], correct_option_id=0
    )
    sent = env.repo.persist_poll_receipt(execution, message)
    env.table.put_item(Item={"PK": f"QUIZ#{CHAT}", "SK": key, "poll_id": "legacy-poll"})
    assert env.repo.finalize_publication(sent)["state"] == "CONFLICT"
    assert env.bot.lookup_poll("poll-0")["correct_option_id"] == 0
    env.answer()
    assert env.process()["state"] == "SCORED"


def test_finalization_database_failure_recovers_without_second_send(quiz_env, monkeypatch):
    env = quiz_env
    original = env.repo.finalize_publication
    monkeypatch.setattr(env.repo, "finalize_publication", Mock(side_effect=RuntimeError("synthetic DB outage")))
    with pytest.raises(RuntimeError):
        publish(env)
    assert env.bot.lookup_poll("poll-0")
    monkeypatch.setattr(env.repo, "finalize_publication", original)
    env.clock.now += 331
    assert publish(env)["status"] == "ok"
    assert len(env.sent) == 1


def test_primary_lookup_write_failure_leaves_unknown_not_another_poll(quiz_env, monkeypatch):
    env = quiz_env
    monkeypatch.setattr(env.repo, "persist_poll_receipt", Mock(side_effect=RuntimeError("synthetic DB outage")))
    with pytest.raises(RuntimeError):
        publish(env)
    env.clock.now += 331
    assert publish(env)["status"] == "unknown"
    assert len(env.sent) == 1


def test_positive_rejection_retries_same_prepared_question(quiz_env):
    env = quiz_env
    env.svc._sender.send_quiz_poll.side_effect = sender_module.PollSendRejected(429)
    assert publish(env)["status"] == "error"
    env.svc._sender.send_quiz_poll.side_effect = env.receipt
    assert publish(env)["status"] == "ok"
    env.svc._generator.generate_question.assert_called_once()


def unknown(env, key="REQUEST#1"):
    execution = env.repo.mark_publication_sending(prepared(env, key))
    msg = env.receipt(chat_id=CHAT, question=question()["question"], options=question()["options"], correct_option_id=0)
    row = env.repo.mark_publication_failed(execution, unknown=True, reason="synthetic")
    return row, msg


@pytest.mark.parametrize(
    "mutation", ["wrong_bot", "wrong_chat", "missing_correct", "multiple", "forwarded", "old_date", "wrong_question"]
)
def test_unknown_reconciliation_requires_full_authoritative_identity(quiz_env, mutation):
    env = quiz_env
    execution, message = unknown(env)
    if mutation == "wrong_bot":
        message["from"]["id"] = 55
    elif mutation == "wrong_chat":
        message["chat"]["id"] = -999
    elif mutation == "missing_correct":
        del message["poll"]["correct_option_ids"]
    elif mutation == "multiple":
        message["poll"]["correct_option_ids"] = [0, 1]
    elif mutation == "forwarded":
        message["forward_origin"] = {"type": "user"}
    elif mutation == "old_date":
        message["date"] -= 86400
    else:
        message["poll"]["question"] = "Other question"
    assert (
        env.svc.reconcile_poll_receipt(CHAT, execution["SK"], execution["generation"], message, 999)["status"]
        == "unknown"
    )
    assert env.bot.lookup_poll("poll-0") is None


def test_reconciliation_uses_returned_option_mapping_and_is_idempotent(quiz_env):
    env = quiz_env
    execution, message = unknown(env)
    message["poll"]["options"].reverse()
    message["poll"]["correct_option_ids"] = [3]
    for _ in range(2):
        assert (
            env.svc.reconcile_poll_receipt(CHAT, execution["SK"], execution["generation"], message, 999)["status"]
            == "ok"
        )
    env.answer(option=3)
    assert env.process()["state"] == "SCORED"
    assert env.bot.get_user_score(CHAT, "7")["total_score"] == 3


def test_two_identical_unknown_send_intents_cannot_be_guessed(quiz_env):
    execution, message = unknown(quiz_env)
    unknown(quiz_env, "REQUEST#2")
    assert (
        quiz_env.svc.reconcile_poll_receipt(CHAT, execution["SK"], execution["generation"], message, 999)["status"]
        == "unknown"
    )


def test_answer_before_lookup_and_legacy_gsi_delay_are_retained(quiz_env, monkeypatch):
    env = quiz_env
    env.answer()
    assert env.process()["state"] == "PENDING"
    assert env.bot.get_answer("poll-0", "7")["attempts"] == 1
    publish(env)
    # Even a broken GSI does not affect primary lookups for V2 publications.
    monkeypatch.setattr(env.bot._table.meta.client, "query", Mock(side_effect=RuntimeError("synthetic index failure")))
    env.clock.now += 300
    assert env.process()["state"] == "SCORED"


def test_database_lookup_failure_is_not_unknown_and_does_not_consume_attempt(quiz_env, monkeypatch):
    env = quiz_env
    env.answer()
    monkeypatch.setattr(env.bot, "lookup_poll", Mock(side_effect=RuntimeError("synthetic DB failure")))
    with pytest.raises(RuntimeError):
        env.process()
    assert env.bot.get_answer("poll-0", "7")["attempts"] == 0


def test_missing_poll_backoff_then_logical_expiry_has_durable_coverage(quiz_env):
    env = quiz_env
    env.answer()
    for _ in range(12):
        env.process()
        env.clock.now += 300
    row = env.bot.get_answer("poll-0", "7")
    assert row["state"] == "UNRESOLVED"
    assert row["next_attempt_at"] > env.clock.now
    env.clock.now = int(row["expires_at"])
    assert env.process()["state"] == "EXPIRED"
    assert env.bot.answer_coverage()["expired"] == 1
    assert env.bot._answer_read(env.bot._answer_outbox_key("poll-0", "7")) == {}


@pytest.mark.parametrize("options", [[], [0, 1], [-1], [True], [12], ["0"]])
def test_retractions_multiple_and_invalid_answers_never_enter_queue(quiz_env, options):
    row = quiz_env.bot.persist_answer({"poll_id": "poll-0", "user": {"id": 7}, "option_ids": options}, 1)
    assert row["state"] == "INVALID"
    assert quiz_env.table.scan()["Items"] == []


def test_answer_outbox_and_score_transaction_failures_are_atomic(quiz_env, monkeypatch):
    env = quiz_env
    publish(env)
    original = env.bot._answer_transaction
    monkeypatch.setattr(env.bot, "_answer_transaction", Mock(side_effect=RuntimeError("synthetic")))
    with pytest.raises(RuntimeError):
        env.answer()
    assert env.bot.get_answer("poll-0", "7") == {}
    monkeypatch.setattr(env.bot, "_answer_transaction", original)
    env.answer()
    monkeypatch.setattr(env.bot, "_answer_transaction", Mock(side_effect=RuntimeError("synthetic")))
    with pytest.raises(RuntimeError):
        env.process()
    assert env.bot.get_user_score(CHAT, "7") is None
    assert env.bot.get_answer("poll-0", "7")["state"] == "PENDING"
    monkeypatch.setattr(env.bot, "_answer_transaction", original)
    assert env.process()["state"] == "SCORED"


def test_concurrent_distinct_answers_cas_retry_preserves_both_scores(quiz_env, monkeypatch):
    env = quiz_env
    publish(env)
    publish(env, 2)
    env.answer("poll-0", update_id=1)
    env.answer("poll-1", update_id=2)
    original, barrier, lock, calls = env.bot.get_user_score, Barrier(2), Lock(), []
    transaction, transaction_lock = env.bot._answer_transaction, Lock()

    def transact(operations):
        # Moto's in-memory rollback snapshot is not thread-safe. Serialize only
        # the atomic server operation; both workers still read the same stale score.
        with transaction_lock:
            return transaction(operations)

    def read(*args):
        result = original(*args)
        with lock:
            calls.append(1)
            should_wait = len(calls) <= 2
        if should_wait:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(env.bot, "get_user_score", read)
    monkeypatch.setattr(env.bot, "_answer_transaction", transact)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(result["state"] == "SCORED" for result in executor.map(env.process, ["poll-0", "poll-1"]))
    assert original(CHAT, "7")["total_score"] == 6
    assert env.bot.answer_coverage()["scored"] == 2


def test_recovery_advances_past_failing_row_and_keeps_outbox(quiz_env):
    env = quiz_env
    env.answer("a-poll")
    env.answer("z-poll")
    queue = Mock()
    queue.send_quiz_answer_task.side_effect = RuntimeError("synthetic queue error")
    with pytest.raises(RuntimeError):
        recover_quiz_answers(repo=env.bot, sqs_repo=queue, limit=1)
    queue.send_quiz_answer_task.side_effect = None
    assert recover_quiz_answers(repo=env.bot, sqs_repo=queue, limit=1)["queued"] == 1
    assert queue.send_quiz_answer_task.call_args.args[0] == "z-poll"
    assert env.bot.get_answer("a-poll", "7")["state"] == "PENDING"


def test_sender_emits_single_answer_protocol_without_transport_retry(monkeypatch):
    response = {"ok": True, "result": {"poll": {"id": "synthetic"}}}
    request = Mock(return_value=Mock(status=200, data=json.dumps(response).encode()))
    monkeypatch.setattr(sender_module.http, "request", request)
    sender = sender_module.QuizSender.__new__(sender_module.QuizSender)
    sender._base_url = "https://synthetic.invalid"
    sender.send_quiz_poll(CHAT, "Question", ["A", "B"], 0)
    body = json.loads(request.call_args.kwargs["body"])
    assert body["correct_option_ids"] == [0]
    assert body["allows_revoting"] is False
    assert body["allows_multiple_answers"] is False
    assert request.call_args.kwargs["retries"] is False


def test_legacy_gsi_miss_retries_then_scores_without_new_primary(quiz_env, monkeypatch):
    env = quiz_env
    env.table.put_item(
        Item={
            "PK": f"QUIZ#{CHAT}",
            "SK": "ONDEMAND#legacy-poll",
            "poll_id": "legacy-poll",
            "options": ["A", "B"],
            "correct_option_id": 1,
            "points": 3,
            "ttl": env.clock.now + 86400,
        }
    )
    env.answer("legacy-poll", option=1)
    lookup = env.bot.lookup_poll
    monkeypatch.setattr(env.bot, "lookup_poll", Mock(return_value=None))
    assert env.process("legacy-poll")["state"] == "PENDING"
    monkeypatch.setattr(env.bot, "lookup_poll", lookup)
    env.clock.now += 300
    assert env.process("legacy-poll")["state"] == "SCORED"
    assert env.bot.get_user_score(CHAT, "7")["week_score"] == 0


def test_expiry_during_score_dependency_read_cannot_commit(quiz_env, monkeypatch):
    env = quiz_env
    publish(env)
    answer = env.answer()
    original = env.bot.get_user_score

    def read(*args):
        result = original(*args)
        env.clock.now = int(answer["expires_at"])
        return result

    monkeypatch.setattr(env.bot, "get_user_score", read)
    assert env.process()["state"] == "EXPIRED"
    assert original(CHAT, "7") is None


def test_publication_recovery_resumes_saved_intent_after_lost_invocation(quiz_env):
    env = quiz_env
    prepared(env)
    env.clock.now += 331
    assert env.svc.recover_publications()["recovered"] == 1
    assert len(env.sent) == 1
    assert env.bot.lookup_poll("poll-0")
    env.svc._generator.generate_question.assert_not_called()


def test_publication_recovery_persists_cursor_before_failing_generation(quiz_env):
    env = quiz_env
    for key in ("REQUEST#1", "REQUEST#2"):
        env.repo.claim_publication(
            CHAT,
            key,
            {"kind": "on_demand", "lang": "en", "topic": "python", "difficulty": "medium", "interactive": False},
        )
    env.clock.now += 331
    env.svc._generator.generate_question.side_effect = RuntimeError("synthetic provider failure")
    with pytest.raises(RuntimeError):
        env.svc.recover_publications(limit=1)
    cursor = env.repo._publication_read({"PK": "QUIZ_PUBLICATION_RECOVERY", "SK": "CURSOR"})
    assert cursor["cursor"]["SK"].endswith("REQUEST#1")
    env.svc._generator.generate_question.side_effect = None
    assert env.svc.recover_publications(limit=1)["recovered"] == 1


def test_pending_coverage_includes_age_and_terminal_expiry(quiz_env):
    env = quiz_env
    row = env.answer()
    env.clock.now += 300
    coverage = env.bot.answer_pending_coverage()
    assert coverage["pending"] == 1 and coverage["oldest_age_seconds"] == 300
    env.clock.now = int(row["expires_at"])
    assert recover_quiz_answers(repo=env.bot, sqs_repo=Mock())["expired"] == 1
    assert env.bot.answer_pending_coverage()["pending"] == 0
    assert env.bot.answer_coverage()["expired"] == 1


@pytest.mark.parametrize("daily", [False, True])
def test_expired_unsent_request_is_terminal_and_not_published(quiz_env, daily):
    env = quiz_env
    key = (
        "DATE#" + datetime.fromtimestamp(env.clock.now, timezone(timedelta(hours=5))).strftime("%Y-%m-%d")
        if daily
        else "REQUEST#1"
    )
    row = prepared(env, key)
    env.clock.now = int(row["expires_at"])
    assert env.svc._publish_request(CHAT, key)["status"] == "expired"
    assert not env.sent
    assert env.repo._publication_read({"PK": "QUIZ_PUBLICATION_OUTBOX", "SK": f"{CHAT}#{key}"}) == {}


def test_late_publication_cannot_overwrite_newer_deck(quiz_env):
    env = quiz_env
    key = {"PK": f"META#category#{CHAT}", "SK": "LATEST"}
    env.table.put_item(Item={**key, "remaining": ["python", "cloud"]})
    env.repo.get_category_queue(CHAT)
    rotation = env.repo.publication_rotations(CHAT, "python", category_remaining=["cloud"])
    execution = env.repo.claim_publication(CHAT, "REQUEST#1", {"kind": "on_demand"})
    execution = env.repo.prepare_publication(execution, env.svc._draft(question(), "python", "en", "medium"), rotation)
    execution = env.repo.mark_publication_sending(execution)
    receipt = env.receipt(
        chat_id=CHAT, question=question()["question"], options=question()["options"], correct_option_id=0
    )
    sent = env.repo.persist_poll_receipt(execution, receipt)
    env.table.put_item(Item={**key, "remaining": ["database"], "publication_generation": "newer"})
    assert env.repo.finalize_publication(sent)["rotation_conflicts"] == 1
    assert env.repo._publication_read(key)["remaining"] == ["database"]
    assert env.bot.lookup_poll("poll-0")


def test_expired_orphan_outbox_after_long_shutdown_is_reaped_with_evidence(quiz_env):
    env = quiz_env
    answer = env.answer()
    env.table.delete_item(Key={"PK": answer["PK"], "SK": answer["SK"]})
    with pytest.raises(RuntimeError):
        recover_quiz_answers(repo=env.bot, sqs_repo=Mock())
    env.clock.now = int(answer["expires_at"])
    assert recover_quiz_answers(repo=env.bot, sqs_repo=Mock())["expired"] == 1
    assert env.bot.answer_coverage()["expired_orphan"] == 1


@pytest.mark.parametrize("ttl", [None, 0, "invalid", True])
def test_malformed_or_expired_poll_ttl_is_not_scoreable(quiz_env, ttl):
    env = quiz_env
    publish(env)
    record = env.bot.lookup_poll("poll-0")
    if ttl is None:
        record.pop("ttl")
    else:
        record["ttl"] = ttl
    env.table.put_item(Item=record)
    assert env.bot.lookup_poll("poll-0") is None


def test_same_scheduled_event_across_midnight_cannot_publish_next_day(quiz_env, monkeypatch):
    env = quiz_env
    env.clock.now = int(datetime(2026, 9, 10, 23, 59, tzinfo=timezone(timedelta(hours=5))).timestamp())
    env.svc._prepare_daily_publication = lambda *args: (env.svc._draft(question(), "python", "en", "medium"), [])
    monkeypatch.setattr(quiz_support.main_module, "_quiz_service", env.svc)
    event = {"chat_ids": [CHAT], "lang": "en", "scheduled_at": "2026-09-10T18:59:00Z"}

    def send(**kwargs):
        env.receipt(**kwargs)
        raise sender_module.PollSendUnknown("synthetic lost acknowledgement")

    env.svc._sender.send_quiz_poll.side_effect = send
    for _ in range(2):
        with pytest.raises(RuntimeError):
            quiz_support.main_module.lambda_handler(event, Mock(aws_request_id="retry"))
        env.clock.now += 120
    assert len(env.sent) == 1
    assert env.repo._publication_read(env.repo.publication_key(CHAT, "DATE#2026-09-10"))["state"] == "UNKNOWN"
    assert env.repo._publication_read(env.repo.publication_key(CHAT, "DATE#2026-09-11")) == {}


def test_daily_missing_scheduler_identity_is_explicit_nonretryable(quiz_env):
    assert quiz_env.svc.process_daily_quiz([CHAT], "en")["retryable"] is False
    assert not quiz_env.sent


@pytest.mark.parametrize("scheduled", [None, "invalid", "2026-09-10T13:00:00", "future"])
def test_bad_scheduler_identity_is_an_observable_lambda_failure(quiz_env, monkeypatch, scheduled):
    env = quiz_env
    if scheduled == "future":
        scheduled = env.clock.now + 301
    monkeypatch.setattr(quiz_support.main_module, "_quiz_service", env.svc)
    event = {"chat_ids": [CHAT], "lang": "en", "scheduled_at": scheduled}
    with pytest.raises(RuntimeError):
        quiz_support.main_module.lambda_handler(event, Mock(aws_request_id="bad-event"))
    assert env.table.scan()["Items"] == []
    env.svc._generator.generate_question.assert_not_called()
    assert not env.sent
