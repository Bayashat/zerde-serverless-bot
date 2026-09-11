"""Original schedule identity and actual webhook/outbox/score recovery integration."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from core.dispatcher import Dispatcher
from services.handlers.quiz import handle_poll_answer
from services.handlers.quiz_reconcile import handle_quiz_reconcile
from services.repositories.sqs import SQSClient
from services.sqs_task_router import process_sqs_event
from webhook import _handle_api_gateway

from tests import quiz_support
from tests.test_infra_configuration import _template

quiz_env = quiz_support.quiz_env


def webhook(quiz_repo, queue):
    bot = Mock()
    dispatcher = Dispatcher(bot, quiz_repo=quiz_repo, sqs_repo=queue)
    dispatcher.on_poll_answer(handle_poll_answer)
    update = {
        "update_id": 99,
        "poll_answer": {"poll_id": "poll-0", "user": {"id": 7, "first_name": "Test"}, "option_ids": [0]},
    }
    with (
        patch("webhook.verify_webhook_secret_token", return_value=True),
        patch("services.memory_v2.runtime.get_memory_ingestion", return_value=None),
        patch("webhook.observe_media_group"),
        patch("webhook.handle_group_agent_update", return_value=False),
    ):
        return _handle_api_gateway({"headers": {}, "body": json.dumps(update)}, dispatcher, bot)


def test_poll_answer_database_failure_returns_retryable_webhook():
    repo = Mock()
    repo.persist_answer.side_effect = RuntimeError("synthetic storage failure")
    queue = Mock()
    assert webhook(repo, queue)["statusCode"] == 500
    queue.send_quiz_answer_task.assert_not_called()


def test_durable_answer_survives_lost_enqueue_and_scores_via_real_router(quiz_env):
    env = quiz_env
    # Valid synthetic Telegram receipt and native DDB publication owner.
    assert (
        env.svc._publish_request(
            "-100123",
            "REQUEST#90",
            {"kind": "on_demand", "lang": "en", "topic": "python", "difficulty": "medium", "interactive": False},
        )["status"]
        == "ok"
    )
    queue = Mock()
    queue.send_quiz_answer_task.side_effect = RuntimeError("synthetic queue outage")
    assert webhook(env.bot, queue)["statusCode"] == 200
    assert env.bot.get_answer("poll-0", "7")["state"] == "PENDING"
    recovered = Mock()
    process_sqs_event(
        {"Records": [{"body": json.dumps({"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER_RECOVERY"})}]},
        Mock(),
        Mock(),
        quiz_repo=env.bot,
        sqs_repo=recovered,
    )
    recovered.send_quiz_answer_task.assert_called_once_with("poll-0", "7")
    task = {"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER", "poll_id": "poll-0", "user_id": "7"}
    for _ in range(2):
        process_sqs_event({"Records": [{"body": json.dumps(task)}]}, Mock(), Mock(), quiz_repo=env.bot)
    assert env.bot.get_answer("poll-0", "7")["state"] == "SCORED"
    assert env.bot.get_user_score("-100123", "7")["total_score"] == 3


def test_quiz_queue_message_contains_references_only(monkeypatch):
    transport = Mock()
    monkeypatch.setattr("services.repositories.sqs._SQS_CLIENT", transport)
    SQSClient().send_quiz_answer_task("poll-0", "7")
    body = json.loads(transport.send_message.call_args.kwargs["MessageBody"])
    assert body == {"schema": 2, "task_type": "PROCESS_QUIZ_ANSWER", "poll_id": "poll-0", "user_id": "7"}
    with pytest.raises(ValueError):
        SQSClient().send_quiz_answer_task("bad/poll", "7")


@pytest.mark.parametrize("env_name,enabled", [("dev", "DISABLED"), ("prod", "ENABLED")])
def test_background_recovery_and_original_schedule_input(monkeypatch, env_name, enabled):
    monkeypatch.setenv("NEWS_CHATS_KK", "-100123")
    monkeypatch.setenv("QUIZ_CHATS_KK", "-100123")
    resources = _template(monkeypatch, env_name=env_name).to_json()["Resources"]
    rules = [r["Properties"] for r in resources.values() if r["Type"] == "AWS::Events::Rule"]
    recoveries = [
        r
        for r in rules
        if r.get("Name", "").startswith(
            ("zerde-serverless-quiz-publication-recovery-", "zerde-serverless-quiz-answer-recovery-")
        )
    ]
    assert len(recoveries) == 2 and all(r["State"] == enabled for r in recoveries)
    if env_name == "prod":
        scheduled = [
            r for r in rules if r.get("Name", "").startswith(("zerde-serverless-news-kk-", "zerde-serverless-quiz-kk-"))
        ]
        assert len(scheduled) == 2
        for rule in scheduled:
            transformer = rule["Targets"][0]["InputTransformer"]
            assert "$.time" in transformer["InputPathsMap"].values()
            assert '"scheduled_at"' in transformer["InputTemplate"]
    failures = [r for r in resources.values() if r["Type"] == "AWS::Lambda::EventInvokeConfig"]
    assert len(failures) >= 2


def test_news_role_has_only_owned_stats_keys(monkeypatch):
    resources = _template(monkeypatch, env_name="prod").to_json()["Resources"]
    statements = [
        s
        for r in resources.values()
        if r["Type"] == "AWS::IAM::Policy"
        for s in r["Properties"]["PolicyDocument"]["Statement"]
    ]
    owned = [
        s
        for s in statements
        if s.get("Condition", {}).get("ForAllValues:StringLike", {}).get("dynamodb:LeadingKeys")
        == ["news_manifest#*", "news_delivery#*"]
    ]
    assert len(owned) == 1 and set(owned[0]["Action"]) == {"dynamodb:GetItem", "dynamodb:UpdateItem"}


def test_reconciliation_requires_live_admin_and_own_bot_poll(monkeypatch):
    monkeypatch.setattr("services.handlers.quiz_reconcile.is_configured_group_chat", lambda _: True)
    monkeypatch.setattr("services.handlers.quiz_reconcile.QUIZ_LAMBDA_NAME", "synthetic-quiz")
    ctx = SimpleNamespace(
        text="/quizreconcile DATE#2026-09-11 " + "a" * 32,
        chat_id=-100123,
        user_id=7,
        message_id=90,
        lang_code="en",
        reply=Mock(),
        bot=Mock(),
        lambda_invoker=Mock(),
        reply_to_message={"from": {"id": 999, "is_bot": True}, "chat": {"id": -100123}, "poll": {"id": "poll-0"}},
    )
    ctx.bot.get_me.return_value = {"id": 999}
    ctx.bot.get_chat_member.return_value = {"status": "member", "user": {"id": 7}}
    handle_quiz_reconcile(ctx)
    ctx.lambda_invoker.invoke.assert_not_called()
    ctx.bot.get_chat_member.return_value["status"] = "administrator"
    ctx.lambda_invoker.invoke.return_value = {"status": "ok"}
    handle_quiz_reconcile(ctx)
    assert ctx.lambda_invoker.invoke.call_args.args[1]["action"] == "reconcile"
    ctx.reply_to_message["from"]["id"] = 998
    handle_quiz_reconcile(ctx)
    assert ctx.lambda_invoker.invoke.call_count == 1
