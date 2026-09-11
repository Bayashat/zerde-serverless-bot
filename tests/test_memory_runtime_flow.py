"""Real source/approval/fact transactions across the integrated bot and worker adapters."""

import asyncio
import json
from unittest.mock import Mock, patch

import boto3
import pytest
from services.memory_v2.extraction_prompt import input_upper_bytes
from services.memory_v2.ingestion import MemoryIngestion, task_payload
from services.memory_v2.models import ExtractionResult, SourceRef
from services.memory_v2.telegram_ingestion import TelegramMemoryAdmission
from services.memory_v2.worker import MemoryWorker
from services.repositories import spam
from services.sqs_task_router import process_sqs_event

from tests import test_memory_v2_contract as contract
from tests.test_memory_v2_contract import CHAT, USER, activate, change

env = contract.env


@pytest.mark.parametrize(
    "score,pending_captcha,queued,accepted",
    [
        (0.3, False, True, False),
        (0.0, False, False, True),
        (0.3, True, False, False),
    ],
)
def test_real_webhook_and_screener_preserve_admission_gate(score, pending_captcha, queued, accepted):
    from webhook import _handle_api_gateway

    ingestion, dispatcher, bot, sqs = Mock(), Mock(), Mock(), Mock()
    ingestion.prepare.return_value = SourceRef("8", 1, "test-epoch")
    dispatcher.captcha_repo.get_pending.return_value = {"state": "PENDING"} if pending_captcha else None
    body = {
        "message": {
            "message_id": 8,
            "date": 2000000000,
            "chat": {"id": CHAT, "type": "supergroup"},
            "from": {"id": int(USER)},
            "text": "I use Python.",
        }
    }
    with (
        patch("services.memory_v2.runtime.get_memory_ingestion", return_value=ingestion),
        patch("webhook._sqs_client", sqs),
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.verify_webhook_secret_token", return_value=True),
        patch("webhook.observe_media_group"),
        patch("webhook.handle_group_agent_update", return_value=False),
        patch("webhook.handle_captcha_answer"),
        patch("services.spam.screening_service.is_chat_admin_or_creator", return_value=False),
        patch("services.spam.screening_service.RuleBasedSpamFilter") as rules,
    ):
        rules.return_value.check.return_value = (score, [])
        result = _handle_api_gateway({"headers": {}, "body": json.dumps(body)}, dispatcher, bot)
    assert result["statusCode"] == 200
    ingestion.observe.assert_called_once()
    assert bool(ingestion.accept_safe.call_count) == accepted
    assert bool(ingestion.prepare.call_count) == queued
    assert bool(sqs.send_spam_check_task.call_count) == queued
    if queued:
        assert sqs.send_spam_check_task.call_args.kwargs["source_ref"] == ingestion.prepare.return_value.as_dict()
        assert ingestion.prepare.call_args.args[0].text == "I use Python."


def test_approved_spam_receipt_promotes_original_source_and_leased_worker_writes_fact(env, monkeypatch):
    activate(env)
    db = boto3.resource("dynamodb", region_name="eu-central-1")
    db.create_table(
        TableName="moderation-runtime-test",
        KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    monkeypatch.setattr(spam, "STATS_TABLE_NAME", "moderation-runtime-test")
    monkeypatch.setattr(spam, "get_dynamodb", lambda: db)
    moderation = spam.SpamRepository()
    queue = Mock()
    ingestion = MemoryIngestion(env.repo, moderation, queue)
    update = {
        "message": {
            "message_id": 8,
            "date": env.clock.now,
            "chat": {"id": CHAT, "type": "supergroup"},
            "from": {"id": int(USER)},
            "text": "I use Python.",
            "reply_to_message": {"text": "A different person's statement", "from": {"id": 77}},
        }
    }
    admission = TelegramMemoryAdmission(ingestion, update)
    combined = "I use Python.\nReplied: A different person's statement"
    context = {"reply_to_text": "A different person's statement"}
    raw_ref = admission.prepare(combined, context)
    body = {
        "task_type": "SPAM_CHECK",
        "chat_id": CHAT,
        "user_id": int(USER),
        "message_id": 8,
        "text": combined,
        "message_context": context,
        "source_ref": raw_ref,
    }
    case = moderation.ensure_case(body)
    owner, case = moderation.claim(case["case_id"])
    moderation.finish_clean(case, owner)
    moderation.release(case["case_id"], owner)
    assert not env.repo.get_source_head(CHAT, "8")
    with (
        patch("services.sqs_task_router.is_configured_group_chat", return_value=True),
        patch("services.sqs_task_router.process_spam_check_task", return_value="clean"),
    ):
        process_sqs_event({"Records": [{"body": json.dumps(body)}]}, Mock(), Mock(), memory_ingestion=ingestion)
    chat_id, ref = queue.send.call_args.args
    assert env.repo.source_snapshot(chat_id, ref)[3]["text"] == "I use Python."
    assert moderation.get(case["case_id"])["recovery_outcome"] == "INGESTED"
    assert moderation.get(case["case_id"])["outbox_pending"] is False

    class Extractor:
        async def extract_batch(self, sources):
            assert [source.text for source in sources] == ["I use Python."]
            return [ExtractionResult(sources[0].ref, (change(),))]

    worker = MemoryWorker(env.repo, lambda validate: Extractor(), sizing_fn=input_upper_bytes)
    result = asyncio.run(
        worker.handle_records([{"messageId": "synthetic-work", "body": json.dumps(task_payload(chat_id, ref))}])
    )
    assert result == {"batchItemFailures": []}
    assert [fact["value"] for fact in env.repo.get_profile(CHAT, USER)] == ["Python"]
    assert env.repo.get_work(chat_id, ref)["state"] == "DONE"


def test_plain_explicit_authorization_transport_failure_returns_webhook_500():
    from services.memory_v2.telegram_api import TelegramReadRetryRequired
    from webhook import _handle_api_gateway

    dispatcher, bot, screener = Mock(), Mock(), Mock()
    dispatcher.captcha_repo.get_pending.return_value = None
    screener.should_screen.return_value = False
    body = {
        "message": {
            "message_id": 90,
            "date": 2000000000,
            "chat": {"id": CHAT, "type": "supergroup"},
            "from": {"id": int(USER)},
            "text": "@zerde_bot Explain SQL",
        }
    }
    with (
        patch("webhook.is_configured_group_chat", return_value=True),
        patch("webhook.verify_webhook_secret_token", return_value=True),
        patch("webhook._spam_screening", return_value=screener),
        patch("services.memory_v2.runtime.get_memory_ingestion", return_value=None),
        patch("webhook.observe_media_group"),
        patch("webhook.handle_group_agent_update", side_effect=TelegramReadRetryRequired("safe read failure")),
    ):
        result = _handle_api_gateway({"headers": {}, "body": json.dumps(body)}, dispatcher, bot)
    assert result["statusCode"] == 500


def test_direct_plain_source_database_failure_is_retryable_before_provider():
    from botocore.exceptions import ClientError
    from services.group_agent import handle_update
    from services.memory_v2.public_answers import MemoryPublicRetryRequiredError

    update = {
        "message": {
            "message_id": 90,
            "date": 2000000000,
            "chat": {"id": CHAT, "type": "supergroup"},
            "from": {"id": int(USER)},
            "text": "Explain SQL",
        }
    }
    with (
        patch("services.group_agent._trigger_kind", return_value="explicit"),
        patch("services.group_agent.detect_media_references", return_value=[]),
        patch("services.memory_v2.public_answers.try_memory_answer", return_value=False),
        patch("services.group_agent.build_explicit_question_context", return_value=Mock()),
        patch(
            "services.memory_v2.explicit_request_gate.capture_configured",
            side_effect=ClientError({"Error": {"Code": "InternalServerError"}}, "GetItem"),
        ),
        patch("services.group_agent.answer_group_question") as provider,
    ):
        with pytest.raises(MemoryPublicRetryRequiredError):
            handle_update(repo=Mock(), bot=Mock(), update=update)
    provider.assert_not_called()
