"""Feedback follows durable Quiz outcomes without owning or retrying publication."""

from unittest.mock import Mock

import pytest

from tests import quiz_support as qs

quiz_env = qs.quiz_env
CHAT = "-100123"
REQUEST = 81
KEY = "REQUEST#81"
OUTBOX = {"PK": "QUIZ_PUBLICATION_OUTBOX", "SK": f"{CHAT}#{KEY}"}


def submit(env, lang="ru", request=REQUEST):
    return env.svc.process_on_demand_quiz_with_feedback(CHAT, lang, "python", "medium", reply_to_message_id=request)


def execution(env):
    return env.repo._publication_read(env.repo.publication_key(CHAT, KEY))


def text(env):
    call = env.svc._sender.send_message.call_args
    assert call.args[0] == CHAT and call.kwargs == {"reply_to_message_id": REQUEST}
    return call.args[1]


@pytest.mark.parametrize("lang", ["en", "kk", "ru", "zh"])
@pytest.mark.parametrize("failure", ["quota", "generation", "rejected"])
def test_confirmed_retained_request_explains_background_retry_and_recovers_once(quiz_env, lang, failure):
    env = quiz_env
    if failure == "quota":
        env.svc._generator.generate_question.side_effect = qs.rate_module.QuizQuotaUnavailable("private detail")
    elif failure == "generation":
        env.svc._generator.generate_question.return_value = None
    else:
        env.svc._sender.send_quiz_poll.side_effect = qs.sender_module.PollSendRejected(429)
    result = submit(env, lang)
    assert result["status"] == "error" and result["feedback_code"] == "queued"
    if failure == "quota":
        assert result["retryable"] is True
    before = execution(env)
    assert before["state"] == ("PREPARED" if failure == "rejected" else "GENERATING")
    assert before["lease_until"] == 0 and not env.sent
    assert env.repo._publication_read(OUTBOX)["generation"] == before["generation"]
    assert env.repo._publication_read(OUTBOX)["next_attempt_at"] == 0
    expected = {
        "en": "You do not need to send it again.",
        "kk": "Қайта жіберудің қажеті жоқ.",
        "ru": "Отправлять запрос заново не нужно.",
        "zh": "无需重新发送。",
    }
    assert expected[lang] in text(env)
    assert result["reason"] not in text(env) and "private detail" not in text(env)
    env.svc._generator.generate_question.side_effect = None
    env.svc._generator.generate_question.return_value = qs.question()
    env.svc._sender.send_quiz_poll.side_effect = env.receipt
    assert env.svc.recover_publications()["recovered"] == 1
    after = execution(env)
    assert after["state"] == "DONE" and after["generation"] == before["generation"]
    assert after["intent"] == before["intent"] and env.repo._publication_read(OUTBOX) == {}
    assert len(env.sent) == 1
    assert env.svc.recover_publications()["recovered"] == 0
    assert submit(env, lang)["status"] == "ok"
    assert len(env.sent) == 1
    env.svc._sender.send_message.assert_called_once()


@pytest.mark.parametrize("failure", [False, None, TimeoutError("private dependency body")])
def test_feedback_delivery_failure_returns_original_error_without_retrying_generation(quiz_env, monkeypatch, failure):
    env = quiz_env
    env.svc._generator.generate_question.side_effect = qs.rate_module.QuizQuotaUnavailable("private reason")
    log = Mock()
    monkeypatch.setattr(qs.service_module, "logger", log)
    snapshots = []

    def feedback(*args, **kwargs):
        snapshots.append((execution(env), env.repo._publication_read(OUTBOX)))
        if isinstance(failure, Exception):
            raise failure
        return failure

    env.svc._sender.send_message.side_effect = feedback
    result = submit(env)
    assert result == {
        "status": "error",
        "reason": "quiz admission unavailable",
        "retryable": True,
        "feedback_code": "queued",
    }
    assert snapshots == [(execution(env), env.repo._publication_read(OUTBOX))]
    env.svc._generator.generate_question.assert_called_once()
    env.svc._sender.send_quiz_poll.assert_not_called()
    assert not env.sent
    log.error.assert_called_once()
    assert "private" not in repr(log.error.call_args)


def test_processing_does_not_claim_a_new_queue_write_or_generate(quiz_env):
    env = quiz_env
    row = env.repo.claim_publication(
        CHAT,
        KEY,
        {"kind": "on_demand", "lang": "ru", "topic": "python", "difficulty": "medium"},
    )
    before = env.repo._publication_read(OUTBOX)
    result = submit(env)
    assert result["status"] == "pending" and result["feedback_code"] == "processing"
    assert "обрабатывается" in text(env) and "Не отправляйте" in text(env)
    assert execution(env) == row and env.repo._publication_read(OUTBOX) == before
    env.svc._generator.generate_question.assert_not_called()
    assert not env.sent


def test_expired_request_allows_new_command_without_generating_or_retaining_work(
    quiz_env,
):
    env = quiz_env
    row = env.repo.claim_publication(
        CHAT,
        KEY,
        {"kind": "on_demand", "lang": "ru", "topic": "python", "difficulty": "medium"},
    )
    env.clock.now = int(row["expires_at"])
    result = submit(env)
    assert result["status"] == "expired" and result["feedback_code"] == "expired"
    assert "истёк" in text(env) and "новую команду" in text(env)
    assert execution(env)["state"] == "EXPIRED" and env.repo._publication_read(OUTBOX) == {}
    env.svc._generator.generate_question.assert_not_called()


def test_unknown_send_requests_admin_review_and_does_not_resend(quiz_env):
    env = quiz_env

    def lost_response(**kwargs):
        env.receipt(**kwargs)
        raise qs.sender_module.PollSendUnknown("private transport error")

    env.svc._sender.send_quiz_poll.side_effect = lost_response
    for _ in range(2):
        result = submit(env)
        assert result["status"] == "unknown" and result["feedback_code"] == "needs_review"
        assert "Администратору" in text(env) and "Не отправляйте" in text(env)
        assert "private" not in text(env)
    assert execution(env)["state"] == "UNKNOWN" and env.repo._publication_read(OUTBOX) == {}
    assert len(env.sent) == 1
    env.svc._generator.generate_question.assert_called_once()


def test_persisted_finalization_conflict_needs_review_but_known_poll_stays_scoreable(
    quiz_env,
):
    env = quiz_env
    env.table.put_item(Item={"PK": f"QUIZ#{CHAT}", "SK": KEY, "poll_id": "another-poll"})
    result = submit(env)
    assert result["status"] == "error" and result["feedback_code"] == "needs_review"
    assert execution(env)["state"] == "CONFLICT" and env.repo._publication_read(OUTBOX) == {}
    assert "Администратору" in text(env)
    assert env.bot.lookup_poll("poll-0")["correct_option_id"] == 0
    env.answer()
    assert env.process()["state"] == "SCORED"
    assert env.bot.get_user_score(CHAT, "7")["total_score"] == 3
    assert submit(env)["status"] == "unknown"
    assert len(env.sent) == 1


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError("uncertain claim"),
        qs.publication.QuizPublicationConflict("lost CAS"),
    ],
)
def test_business_failure_propagates_without_fabricating_feedback(quiz_env, monkeypatch, error):
    env = quiz_env
    monkeypatch.setattr(env.repo, "claim_publication", Mock(side_effect=error))
    with pytest.raises(type(error)) as raised:
        submit(env)
    assert raised.value is error
    env.svc._sender.send_message.assert_not_called()
    env.svc._generator.generate_question.assert_not_called()
    assert execution(env) == {}


def test_rejected_missing_identity_is_not_called_queued(quiz_env):
    env = quiz_env
    result = submit(env, request=None)
    assert result["retryable"] is False and result["feedback_code"] == "rejected"
    assert "не была принята" in env.svc._sender.send_message.call_args.args[1]
    env.svc._generator.generate_question.assert_not_called()
    assert env.table.scan()["Items"] == []


@pytest.mark.parametrize("code", [None, "future_outcome", ["queued"]])
def test_unknown_feedback_does_not_guess_from_reason_or_retryable(quiz_env, monkeypatch, code):
    env = quiz_env
    result = {
        "status": "error",
        "retryable": True,
        "reason": "private dependency body",
        "feedback_code": code,
    }
    monkeypatch.setattr(env.svc, "process_on_demand_quiz", Mock(return_value=result))
    assert submit(env) is result
    assert "Не удалось подтвердить" in text(env) and "private" not in text(env)
    assert env.table.scan()["Items"] == []


def test_real_feedback_sender_omits_transport_body_from_final_logs(quiz_env, monkeypatch):
    import logging

    from zerde_common.logger import JSONFormatter

    env = quiz_env
    env.svc._generator.generate_question.side_effect = qs.rate_module.QuizQuotaUnavailable()
    sender = qs.sender_module.QuizSender.__new__(qs.sender_module.QuizSender)
    sender._base_url = "https://api.telegram.org/bot123456:synthetic_token_abcdefghijklmnopqrstuvwxyz"
    transport = Mock(side_effect=TimeoutError("synthetic private dependency body"))
    monkeypatch.setattr(qs.sender_module.http, "request", transport)
    env.svc._sender = sender
    formatted = []

    class Capture(logging.Handler):
        def emit(self, record):
            formatted.append(JSONFormatter().format(record))

    for module in [qs.sender_module, qs.service_module]:
        monkeypatch.setattr(module.logger.logger, "handlers", [Capture()])
        monkeypatch.setattr(module.logger.logger, "level", logging.DEBUG)
    result = submit(env)
    assert result["status"] == "error" and result["feedback_code"] == "queued"
    assert execution(env)["state"] == "GENERATING"
    assert env.repo._publication_read(OUTBOX)["generation"] == execution(env)["generation"]
    env.svc._generator.generate_question.assert_called_once()
    transport.assert_called_once()
    assert transport.call_args.args[1].endswith("/sendMessage")
    assert transport.call_args.kwargs["retries"] is False and not env.sent
    assert len(formatted) == 2 and "TimeoutError" in formatted[0]
    assert all("synthetic private dependency body" not in row and sender._base_url not in row for row in formatted)


@pytest.mark.parametrize("delivery", [False, TimeoutError("synthetic send failure")])
def test_diagnostic_failure_also_cannot_retry_the_business_call(quiz_env, monkeypatch, delivery):
    env = quiz_env
    env.svc._generator.generate_question.return_value = None
    if isinstance(delivery, Exception):
        env.svc._sender.send_message.side_effect = delivery
    else:
        env.svc._sender.send_message.return_value = delivery
    log = Mock()
    log.error.side_effect = RuntimeError("synthetic logging outage")
    monkeypatch.setattr(qs.service_module, "logger", log)
    result = submit(env)
    assert result["status"] == "error" and result["feedback_code"] == "queued"
    env.svc._generator.generate_question.assert_called_once()
    env.svc._sender.send_message.assert_called_once()
    assert execution(env)["state"] == "GENERATING" and env.repo._publication_read(OUTBOX)
    assert not env.sent
