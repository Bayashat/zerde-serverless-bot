"""Real SDK state transitions and fake-only Telegram notification outcomes."""

import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

sys.path.insert(0, str(Path("src/operations").resolve()))
import operations_notifications as notifications  # noqa: E402
from operations_state import DeliveryBusyError, DeliveryRepository  # noqa: E402

_spec = importlib.util.spec_from_file_location("operations_entrypoint", "src/operations/main.py")
entrypoint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entrypoint)

TOPIC = "arn:aws:sns:eu-central-1:123456789012:zerde-serverless-operations-prod"
ALARM = "zerde-serverless-bot-prod-errors"
STAMP = "2026-09-10T12:00:00+00:00"
NOW = 1789041600


@pytest.fixture(autouse=True)
def config(monkeypatch):
    for key, value in {
        "OPERATIONS_TOPIC_ARN": TOPIC,
        "ENVIRONMENT": "prod",
        "AWS_REGION": "eu-central-1",
        "OPERATIONS_ACCOUNT_ID": "123456789012",
        "OPERATIONS_ALARM_NAMES": json.dumps([ALARM]),
        "ADMIN_USER_ID": "123",
        "BOT_TOKEN": "123:synthetic-token",
        "SSM_SECRET_PREFIX": "",
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_EC2_METADATA_DISABLED": "true",
    }.items():
        monkeypatch.setenv(key, value)


def record(**changes):
    body = {
        "AlarmName": ALARM,
        "AWSAccountId": "123456789012",
        "AlarmArn": f"arn:aws:cloudwatch:eu-central-1:123456789012:alarm:{ALARM}",
        "StateChangeTime": STAMP,
        "NewStateValue": "ALARM",
        "OldStateValue": "OK",
        **changes,
    }
    return {
        "EventSource": "aws:sns",
        "Sns": {
            "TopicArn": TOPIC,
            "MessageId": "event-1",
            "Timestamp": STAMP,
            "Message": json.dumps(body),
        },
    }


def test_only_fault_and_actual_recovery_are_rendered_without_provider_reason():
    notice = notifications.parse_notice(record(NewStateReason="raw sensitive payload"), now=NOW)
    assert "故障" in notice.text and "raw sensitive" not in notice.text
    assert "恢复" in notifications.parse_notice(record(NewStateValue="OK", OldStateValue="ALARM"), now=NOW).text
    assert notifications.parse_notice(record(NewStateValue="OK", OldStateValue="INSUFFICIENT_DATA"), now=NOW) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"AlarmName": "other-project"},
        {"AWSAccountId": "111111111111"},
        {"AlarmArn": "wrong-arn"},
        {"StateChangeTime": "2026-09-11T12:00:00Z"},
        {"StateChangeTime": "2026-08-01T12:00:00Z"},
        {"StateChangeTime": "2026-09-10T12:00:00"},
    ],
)
def test_spoofed_or_stale_alarm_is_visible_failure(changes):
    with pytest.raises(ValueError):
        notifications.parse_notice(record(**changes), now=NOW)


def test_untrusted_sns_topic_never_reaches_a_destination():
    value = record()
    value["Sns"]["TopicArn"] = "other-topic"
    with pytest.raises(ValueError):
        notifications.parse_notice(value, now=NOW)


def test_budget_event_binds_the_owner_scope_period_and_threshold():
    value = record()
    budget = {
        "schema": "zerde.operations.v1",
        "kind": "budget",
        "project": "ZerdeBot",
        "environment": "prod",
        "component": "memory-v2",
        "budget_scope": "incremental_aws",
        "threshold_percent": 80,
        "status": "warning",
        "period": "2026-09",
        "observed_at": STAMP,
        "text": "arbitrary untrusted text",
        "chat_id": -100123,
    }
    value["Sns"]["Message"] = json.dumps(budget)
    notice = notifications.parse_notice(value, now=NOW)
    assert "增量估算" in notice.text and "arbitrary" not in notice.text
    value["Sns"]["Message"] = json.dumps({**budget, "budget_scope": "model"})
    model_notice = notifications.parse_notice(value, now=NOW)
    assert "全项目模型" in model_notice.text and "触发环境：prod" in model_notice.text
    for change in ({"period": "2026-08"}, {"budget_scope": "account"}, {"threshold_percent": True}):
        value["Sns"]["Message"] = json.dumps({**budget, **change})
        with pytest.raises(ValueError):
            notifications.parse_notice(value, now=NOW)


@pytest.mark.parametrize("admin", ["", "0", "-100123", "channel-name"])
def test_admin_target_must_be_a_positive_private_id(monkeypatch, admin):
    monkeypatch.setenv("ADMIN_USER_ID", admin)
    http = MagicMock()
    monkeypatch.setattr(notifications, "_http", http)
    with pytest.raises(ValueError):
        notifications.send_private("synthetic")
    http.request.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(status=400, data=b"private response body"),
        SimpleNamespace(status=429, data=b"private response body"),
        SimpleNamespace(status=200, data=b'{"ok":false}'),
        SimpleNamespace(status=200, data=b'{"ok":true,"result":{"message_id":1,"chat":{"id":-1,"type":"group"}}}'),
    ],
)
def test_unconfirmed_delivery_raises_without_raw_response(monkeypatch, response):
    http = MagicMock()
    http.request.return_value = response
    monkeypatch.setattr(notifications, "_http", http)
    with pytest.raises(RuntimeError) as exc:
        notifications.send_private("synthetic")
    assert "private response body" not in str(exc.value)


def test_send_has_fixed_endpoint_private_target_and_no_hidden_retry(monkeypatch):
    http = MagicMock()
    http.request.return_value = SimpleNamespace(
        status=200,
        data=json.dumps(
            {
                "ok": True,
                "result": {"message_id": 1, "chat": {"id": 123, "type": "private"}},
            }
        ).encode(),
    )
    monkeypatch.setattr(notifications, "_http", http)
    notifications.send_private("synthetic")
    args, kwargs = http.request.call_args
    assert args[1] == "https://api.telegram.org/bot123:synthetic-token/sendMessage"
    assert json.loads(kwargs["body"]) == {"chat_id": 123, "text": "synthetic"}
    assert kwargs["retries"] is False


@pytest.fixture
def repository(monkeypatch):
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
        table = dynamodb.create_table(
            TableName="operations-test",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setenv("STATS_TABLE_NAME", table.name)
        yield DeliveryRepository(table)


def test_actual_sdk_serializes_dedup_ordering_and_expired_lease_fence(repository, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1000)
    key, old = repository.claim("stream", 1)
    with pytest.raises(DeliveryBusyError):
        repository.claim("stream", 2)
    monkeypatch.setattr(time, "time", lambda: 1091)
    _, new = repository.claim("stream", 2)
    with pytest.raises(ClientError):
        repository.confirm(key, old, 1)
    repository.release(key, old)
    repository.confirm(key, new, 2)
    assert repository.claim("stream", 2) is None
    assert repository.claim("stream", 1) is None
    assert key.startswith("operations#")
    assert repository.table.scan()["Count"] == 1


def test_failed_send_retries_then_duplicate_event_sends_once(repository, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW)
    send = MagicMock(side_effect=[TimeoutError("https://bot123:secret/sendMessage"), None])
    monkeypatch.setattr(entrypoint, "send_private", send)
    event = {"Records": [record()]}
    with pytest.raises(RuntimeError) as exc:
        entrypoint.lambda_handler(event, None)
    assert "secret" not in "".join(traceback.format_exception(exc.value))
    entrypoint.lambda_handler(event, None)
    entrypoint.lambda_handler(event, None)
    assert send.call_count == 2


def test_newer_budget_pause_blocks_late_warning_through_parser_and_actual_repository(repository, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: NOW + 120)
    send = MagicMock()
    monkeypatch.setattr(entrypoint, "send_private", send)

    def event(threshold, status, observed):
        value = record()
        value["Sns"]["Timestamp"] = observed
        value["Sns"]["Message"] = json.dumps(
            {
                "schema": "zerde.operations.v1",
                "kind": "budget",
                "project": "ZerdeBot",
                "environment": "prod",
                "component": "memory-v2",
                "budget_scope": "incremental_aws",
                "threshold_percent": threshold,
                "status": status,
                "period": "2026-09",
                "observed_at": observed,
            }
        )
        return {"Records": [value]}

    newer = event(90, "paused", "2026-09-10T12:01:00Z")
    older = event(80, "warning", STAMP)
    entrypoint.lambda_handler(newer, None)
    entrypoint.lambda_handler(older, None)
    entrypoint.lambda_handler(newer, None)
    assert send.call_count == 1
    assert "90% · paused" in send.call_args.args[0]
    assert repository.table.scan()["Count"] == 1


def test_storage_failure_never_sends_and_is_not_acknowledged(monkeypatch):
    repo = MagicMock()
    repo.claim.side_effect = RuntimeError("DDB down")
    monkeypatch.setattr(entrypoint, "DeliveryRepository", lambda table: repo)
    monkeypatch.setattr(entrypoint.boto3, "resource", MagicMock())
    monkeypatch.setattr(time, "time", lambda: NOW)
    send = MagicMock()
    monkeypatch.setattr(entrypoint, "send_private", send)
    with pytest.raises(RuntimeError):
        entrypoint.lambda_handler({"Records": [record()]}, None)
    send.assert_not_called()
