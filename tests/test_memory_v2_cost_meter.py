"""Real botocore event/retry paths with fake wire responses; no AWS/network calls."""

import asyncio
import json
import weakref
from types import SimpleNamespace

import boto3
import pytest
from botocore.awsrequest import AWSResponse
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from services.memory_v2 import cost_meter as module
from services.memory_v2.cost_meter import CostInventory, InvocationCostMeter, register_client
from zerde_common.logger import JSONFormatter


class Raw:
    def __init__(self, body):
        self.body = body

    def stream(self, *args, **kwargs):
        yield self.body


def response(request, payload=None, status=200):
    body = json.dumps(payload or {}).encode()
    return AWSResponse(request.url, status, {"content-type": "application/x-amz-json-1.0"}, Raw(body))


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(module, "_CLIENTS", weakref.WeakKeyDictionary())
    monkeypatch.setattr(module, "_REGISTRATION_FAILED", False)
    module._SCOPE.set(None)
    module._CALLS.set(())
    monkeypatch.setattr("botocore.endpoint.time.sleep", lambda seconds: None)
    clients = {}
    calls = []
    for service in ("dynamodb", "sqs"):
        client = boto3.client(
            service,
            region_name="eu-central-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            config=Config(retries={"total_max_attempts": 1, "mode": "standard"}),
        )
        assert register_client(client)
        clients[service] = client

        def send(request):
            calls.append(json.loads(request.body))
            return response(request)

        monkeypatch.setattr(client._endpoint.http_session, "send", send)
    inventory = CostInventory(
        "shared-stats",
        "https://sqs.eu-central-1.amazonaws.com/123456789012/main",
        frozenset({"memory-v2", "business-only"}),
        frozenset({"https://sqs.eu-central-1.amazonaws.com/123456789012/memory-v2"}),
        "synthetic-inventory-hash",
        factory_coverage_verified=True,
        shared_stats_index_count=0,
        shared_stats_replica_count=0,
    )
    records = []
    clock = SimpleNamespace(now=10.0)
    meter = InvocationCostMeter(
        SimpleNamespace(aws_request_id="00000000-0000-0000-0000-000000000001"),
        inventory,
        emit=records.append,
        clock=lambda: clock.now,
    )
    yield SimpleNamespace(
        meter=meter,
        inventory=inventory,
        records=records,
        clock=clock,
        ddb=clients["dynamodb"],
        sqs=clients["sqs"],
        calls=calls,
    )


def get(env, table="shared-stats"):
    return env.ddb.get_item(TableName=table, Key={"pk": {"S": "SYNTHETIC-SECRET-KEY"}})


def final(env):
    env.meter.finish()
    return env.records[-1]


def test_exact_outer_log_fields_first_touch_once_and_final_once(env):
    with env.meter.span():
        get(env)
        with env.meter.span():
            get(env)
    with env.meter.span():
        get(env)
    env.clock.now += 0.0011
    result = final(env)
    env.meter.finish()
    assert len(env.records) == 2
    assert env.records[0] == {
        "cost_event": "MemoryV2CostStart",
        "cost_schema": 1,
        "request_id": env.meter.request_id,
        "memory_request": 1,
    }
    assert result == {
        "cost_event": "MemoryV2Cost",
        "cost_schema": 1,
        "request_id": env.meter.request_id,
        "complete": 1,
        "elapsed_ms": 2,
        "shared_stats_rru": 300,
        "shared_stats_wru": 0,
        "shared_sqs_units": 0,
    }
    assert "SYNTHETIC-SECRET-KEY" not in json.dumps(env.records)
    assert "shared-stats" not in json.dumps(env.records) and "QueueUrl" not in json.dumps(env.records)


def test_calls_outside_spans_and_untouched_invocation_emit_no_markers(env):
    get(env)
    env.meter.finish()
    assert env.records == [] and "ReturnConsumedCapacity" not in env.calls[0]


def test_dedicated_table_and_queue_are_excluded_while_calling_shared_is_counted(env):
    with env.meter.span():
        get(env, "memory-v2")
        env.sqs.send_message(QueueUrl=next(iter(env.inventory.excluded_queue_urls)), MessageBody="reference-only")
        env.sqs.send_message(QueueUrl=env.inventory.shared_main_queue_url, MessageBody="reference-only")
    result = final(env)
    assert result["complete"] == 1 and result["shared_stats_rru"] == 0 and result["shared_sqs_units"] == 115


def test_sdk_requests_consumed_capacity_without_downgrading_indexes(env):
    with env.meter.span():
        get(env)
        env.ddb.get_item(TableName="shared-stats", Key={"pk": {"S": "x"}}, ReturnConsumedCapacity="INDEXES")
    assert [call["ReturnConsumedCapacity"] for call in env.calls] == ["TOTAL", "INDEXES"]


def test_complete_success_capacity_refunds_only_last_of_two_wire_attempts(env, monkeypatch):
    client = boto3.client(
        "dynamodb",
        region_name="eu-central-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        config=Config(retries={"total_max_attempts": 2, "mode": "standard"}),
    )
    assert register_client(client)
    attempts = []

    def send(request):
        attempts.append(1)
        if len(attempts) == 1:
            return response(request, {"__type": "InternalServerError", "message": "synthetic-failure"}, 500)
        return response(
            request,
            {
                "ConsumedCapacity": {
                    "TableName": "shared-stats",
                    "ReadCapacityUnits": 0.5,
                    "WriteCapacityUnits": 0,
                    "CapacityUnits": 0.5,
                }
            },
        )

    monkeypatch.setattr(client._endpoint.http_session, "send", send)
    with env.meter.span():
        client.get_item(TableName="shared-stats", Key={"pk": {"S": "x"}})
    result = final(env)
    assert len(attempts) == 2 and result["complete"] == 1
    assert result["shared_stats_rru"] == 100.5  # Unknown first attempt is never refunded.


def test_failed_response_and_transport_failure_keep_upper_and_finalize(env, monkeypatch):
    monkeypatch.setattr(
        env.ddb._endpoint.http_session,
        "send",
        lambda request: response(
            request,
            {
                "__type": "ConditionalCheckFailedException",
                "ConsumedCapacity": {"TableName": "shared-stats", "ReadCapacityUnits": 0, "WriteCapacityUnits": 0},
            },
            400,
        ),
    )
    with env.meter.span():
        with pytest.raises(ClientError):
            env.ddb.put_item(TableName="shared-stats", Item={"pk": {"S": "x"}})
    assert final(env)["shared_stats_wru"] == 400
    assert env.records[-1]["shared_stats_rru"] == 100


def test_transport_failure_is_not_a_zero_cost_attempt(env, monkeypatch):
    def fail(request):
        raise EndpointConnectionError(endpoint_url="https://synthetic.invalid")

    monkeypatch.setattr(env.ddb._endpoint.http_session, "send", fail)
    with env.meter.span():
        with pytest.raises(EndpointConnectionError):
            get(env)
    result = final(env)
    assert result["complete"] == 1 and result["shared_stats_rru"] == 100


def test_mixed_transaction_only_shared_actions_count_and_success_exact_capacity_settles(env, monkeypatch):
    with env.meter.span():
        env.ddb.transact_write_items(
            TransactItems=[
                {
                    "ConditionCheck": {
                        "TableName": "shared-stats",
                        "Key": {"pk": {"S": "a"}},
                        "ConditionExpression": "attribute_exists(pk)",
                    }
                },
                {"Put": {"TableName": "shared-stats", "Item": {"pk": {"S": "b"}}}},
                {"Put": {"TableName": "memory-v2", "Item": {"pk": {"S": "c"}}}},
            ]
        )
    result = final(env)
    assert result["shared_stats_rru"] == 400 and result["shared_stats_wru"] == 800


def test_batch_bounds_and_shared_consumer_upper(env):
    with env.meter.span():
        env.ddb.batch_get_item(RequestItems={"shared-stats": {"Keys": [{"pk": {"S": "a"}}, {"pk": {"S": "b"}}]}})
        env.ddb.batch_write_item(RequestItems={"shared-stats": [{"PutRequest": {"Item": {"pk": {"S": "c"}}}}]})
        env.sqs.send_message_batch(
            QueueUrl=env.inventory.shared_main_queue_url,
            Entries=[{"Id": "1", "MessageBody": "x"}, {"Id": "2", "MessageBody": "y"}],
        )
        env.sqs.receive_message(QueueUrl=env.inventory.shared_main_queue_url, MaxNumberOfMessages=10)
        env.sqs.delete_message(QueueUrl=env.inventory.shared_main_queue_url, ReceiptHandle="synthetic-handle")
    result = final(env)
    assert result["shared_stats_rru"] == 600 and result["shared_stats_wru"] == 800
    assert result["shared_sqs_units"] == 2 * 115 + 160 + 1


def test_actual_prepared_wire_body_controls_scope_not_earlier_api_parameters(env):
    def change_scope(request, **kwargs):
        body = json.loads(request.body)
        body["TableName"] = "not-in-inventory"
        request.body = json.dumps(body).encode()

    env.ddb.meta.events.register_first("before-send.dynamodb.GetItem", change_scope)
    with env.meter.span():
        get(env)
    assert final(env)["complete"] == 0


def test_unknown_resource_operation_or_wire_shape_is_incomplete(env):
    with env.meter.span():
        get(env, "unknown-table")
        env.ddb.describe_table(TableName="shared-stats")
    assert final(env)["complete"] == 0


@pytest.mark.parametrize("operation", ["describe_table", "describe_continuous_backups"])
@pytest.mark.parametrize("table", ["memory-v2", "shared-stats", "unknown-table"])
def test_monitor_metadata_api_has_exact_dedicated_owner_only(env, operation, table):
    with env.meter.span():
        getattr(env.ddb, operation)(TableName=table)
    result = final(env)
    assert result["complete"] == int(table == "memory-v2")
    assert result["shared_stats_rru"] == result["shared_stats_wru"] == result["shared_sqs_units"] == 0
    assert "ReturnConsumedCapacity" not in env.calls[0]


def test_unknown_sqs_api_is_not_silently_zero(env):
    with env.meter.span():
        env.sqs.list_queues()
    assert final(env)["complete"] == 0


def test_hook_registration_failure_and_missing_factory_proof_are_incomplete(env):
    assert register_client(None) is False
    with env.meter.span():
        get(env)
    assert final(env)["complete"] == 0


def test_missing_required_client_hook_is_not_assumed_zero(env, monkeypatch):
    monkeypatch.setattr(module, "_CLIENTS", weakref.WeakKeyDictionary({env.ddb: "dynamodb"}))
    with env.meter.span():
        get(env)
    assert final(env)["complete"] == 0


def test_unknown_inventory_and_finish_before_scope_drains_are_incomplete(env):
    env.meter.complete = False
    with env.meter.span():
        get(env)
        env.meter.finish()
    assert env.records[-1]["complete"] == 0


def test_async_to_thread_context_is_propagated_and_attempt_totals_are_isolated(env):
    async def run():
        with env.meter.span():
            await asyncio.gather(*(asyncio.to_thread(get, env) for _ in range(4)))

    asyncio.run(run())
    result = final(env)
    assert result["complete"] == 1 and result["shared_stats_rru"] == 400
    assert len(env.records) == 2


def test_shared_json_formatter_exposes_meter_schema_at_outer_level(env):
    import logging

    with env.meter.span():
        get(env)
    result = final(env)
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "Memory V2 cost observation", (), None)
    record._extra = result
    formatted = json.loads(JSONFormatter().format(record))
    assert formatted["cost_event"] == "MemoryV2Cost" and formatted["request_id"] == env.meter.request_id
    assert formatted["shared_stats_rru"] == 100 and "SYNTHETIC-SECRET-KEY" not in json.dumps(formatted)


def test_query_and_scan_reserve_one_mebibyte_strong_read_each(env):
    with env.meter.span():
        env.ddb.query(
            TableName="shared-stats", KeyConditionExpression="pk = :pk", ExpressionAttributeValues={":pk": {"S": "x"}}
        )
        env.ddb.scan(TableName="shared-stats")
    assert final(env)["shared_stats_rru"] == 512


def test_incomplete_consumed_capacity_cannot_refund_known_upper(env, monkeypatch):
    monkeypatch.setattr(
        env.ddb._endpoint.http_session,
        "send",
        lambda request: response(request, {"ConsumedCapacity": {"TableName": "shared-stats", "CapacityUnits": 0.5}}),
    )
    with env.meter.span():
        get(env)
    assert final(env)["shared_stats_rru"] == 100


def test_invalid_consumed_capacity_cannot_make_totals_negative(env, monkeypatch):
    monkeypatch.setattr(
        env.ddb._endpoint.http_session,
        "send",
        lambda request: response(
            request,
            {"ConsumedCapacity": {"TableName": "shared-stats", "ReadCapacityUnits": -1000, "WriteCapacityUnits": 0}},
        ),
    )
    with env.meter.span():
        get(env)
    assert final(env)["shared_stats_rru"] == 100


def test_nested_sdk_calls_refund_their_own_call_state(env, monkeypatch):
    def nested(request):
        env.sqs.send_message(QueueUrl=env.inventory.shared_main_queue_url, MessageBody="ref")
        return response(
            request,
            {"ConsumedCapacity": {"TableName": "shared-stats", "ReadCapacityUnits": 1, "WriteCapacityUnits": 0}},
        )

    monkeypatch.setattr(env.ddb._endpoint.http_session, "send", nested)
    with env.meter.span():
        get(env)
    result = final(env)
    assert result["complete"] == 1 and result["shared_stats_rru"] == 1 and result["shared_sqs_units"] == 115
    assert module._CALLS.get() == ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("factory_coverage_verified", False),
        ("shared_stats_index_count", None),
        ("shared_stats_index_count", 1),
        ("shared_stats_replica_count", 1),
        ("main_queue_max_receive_count", 5),
        ("version", ""),
    ],
)
def test_unconfirmed_inventory_preconditions_make_final_incomplete(env, field, value):
    from dataclasses import replace

    inventory = replace(env.inventory, **{field: value})
    records = []
    meter = InvocationCostMeter(
        SimpleNamespace(aws_request_id="00000000-0000-0000-0000-000000000002"), inventory, emit=records.append
    )
    with meter.span():
        get(env)
    meter.finish()
    assert records[-1]["complete"] == 0 and records[-1]["shared_stats_rru"] == 100


def test_malformed_actual_wire_json_is_unverified(env):
    def malformed(request, **kwargs):
        request.body = b"not-json"

    env.ddb.meta.events.register_first("before-send.dynamodb.GetItem", malformed)
    # Fake transport does not parse this deliberately malformed payload.
    env.ddb._endpoint.http_session.send = lambda request: response(request)
    with env.meter.span():
        get(env)
    assert final(env)["complete"] == 0


def test_log_budget_overrun_and_missing_context_id_are_unverified(env):
    with env.meter.span():
        get(env)
    env.meter.log_bytes = 64 * 1024
    assert final(env)["complete"] == 0
    records = []
    meter = InvocationCostMeter(SimpleNamespace(), env.inventory, emit=records.append)
    with meter.span():
        pass
    meter.finish()
    assert records[-1]["complete"] == 0 and records[-1]["request_id"] == ""


def test_warm_invocations_do_not_accumulate_prior_request_units(env):
    with env.meter.span():
        get(env)
    assert final(env)["shared_stats_rru"] == 100
    assert register_client(env.ddb)  # Idempotent factory reuse must not double hook.
    records = []
    other = InvocationCostMeter(
        SimpleNamespace(aws_request_id="00000000-0000-0000-0000-000000000002"), env.inventory, emit=records.append
    )
    with other.span():
        get(env)
    other.finish()
    assert records[-1]["shared_stats_rru"] == 100 and len(records) == 2


def test_real_dynamodb_resource_serialization_and_native_transaction_keep_meter_hooks(env):
    from dataclasses import replace

    from moto import mock_aws

    with mock_aws():
        db = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="testing", aws_secret_access_key="testing"
        )
        assert register_client(db.meta.client)
        table = db.create_table(
            TableName="shared-stats",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        records = []
        meter = InvocationCostMeter(
            SimpleNamespace(aws_request_id="00000000-0000-0000-0000-000000000003"),
            replace(env.inventory),
            emit=records.append,
        )
        with meter.span():
            table.put_item(Item={"pk": "native", "value": 1})
            assert table.get_item(Key={"pk": "native"})["Item"]["value"] == 1
            db.meta.client.transact_write_items(
                TransactItems=[
                    {
                        "ConditionCheck": {
                            "TableName": table.name,
                            "Key": {"pk": "native"},
                            "ConditionExpression": "attribute_exists(pk)",
                        }
                    }
                ]
            )
        meter.finish()
        assert records[-1]["complete"] == 1
        assert records[-1]["shared_stats_rru"] > 0 and records[-1]["shared_stats_wru"] > 0


def test_duplicate_json_properties_cannot_hide_shared_resource(env):
    def duplicate(request, **kwargs):
        request.body = b'{"TableName":"shared-stats","TableName":"memory-v2"}'

    env.ddb.meta.events.register_first("before-send.dynamodb.GetItem", duplicate)
    env.ddb._endpoint.http_session.send = lambda request: response(request)
    with env.meter.span():
        get(env)
    assert final(env)["complete"] == 0
