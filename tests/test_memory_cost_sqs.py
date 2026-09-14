"""Real botocore serialization/parsing with synthetic wire replies; no AWS calls."""

import io
import json
from contextlib import closing
from unittest.mock import patch

import boto3
import pytest
from botocore.awsrequest import AWSResponse
from botocore.config import Config
from botocore.exceptions import ClientError
from moto.core.models import botocore_stubber
from services.memory_budget import MemoryBudgetPaused
from services.memory_v2._cost_catalog import UnverifiedCost

from tests import test_memory_cost_monitor

budget = test_memory_cost_monitor.budget
monitor = test_memory_cost_monitor.monitor

QUEUE_ATTRIBUTES = ["QueueArn", "CreatedTimestamp", "MaximumMessageSize", "KmsMasterKeyId"]


class WireBody(io.BytesIO):
    def stream(self, amt=None, decode_content=False):
        yield self.read()


def wire_response(request, status, body):
    return AWSResponse(
        request.url,
        status,
        {"content-type": "application/x-amz-json-1.0"},
        WireBody(json.dumps(body).encode()),
    )


def sqs_client():
    client = boto3.client(
        "sqs",
        region_name="eu-central-1",
        aws_access_key_id="synthetic-access",
        aws_secret_access_key="synthetic-secret",
        config=Config(retries={"max_attempts": 0}, connect_timeout=1, read_timeout=1),
    )
    # Moto owns only the budget table in these tests. This SQS client must use
    # our synthetic HTTP reply through botocore's real serializer/parser.
    client.meta.events.unregister("before-send", botocore_stubber)
    return client


def attributes(url, start):
    # Actual standard-queue shape: absent FifoQueue and absent KmsMasterKeyId.
    return {
        "QueueArn": "arn:aws:sqs:eu-central-1:123456789012:" + url.rsplit("/", 1)[-1],
        "CreatedTimestamp": str(start),
        "MaximumMessageSize": "1048576",
    }


def test_standard_queue_fifo_only_request_reproduces_error_and_reader_uses_supported_request(budget):
    service, _, _ = monitor(budget)
    inventory = service.inventory
    calls = []

    def send(request):
        body = json.loads(request.body)
        calls.append(body)
        if "FifoQueue" in body["AttributeNames"]:
            return wire_response(request, 400, {"__type": "InvalidAttributeName", "message": "Invalid attribute"})
        assert body["AttributeNames"] == QUEUE_ATTRIBUTES
        return wire_response(
            request, 200, {"Attributes": attributes(body["QueueUrl"], inventory.value["metering_started_at"])}
        )

    with closing(sqs_client()) as client, patch.object(client._endpoint.http_session, "send", side_effect=send):
        with pytest.raises(ClientError) as original:
            client.get_queue_attributes(
                QueueUrl=inventory.queues[0]["url"],
                AttributeNames=[*QUEUE_ATTRIBUTES[:3], "FifoQueue", "KmsMasterKeyId"],
            )
        assert original.value.response["Error"]["Code"] == "InvalidAttributeName"
        service.telemetry.sqs = client
        metadata = service.telemetry.resources()
    assert len(calls) == 5
    assert [call["QueueUrl"] for call in calls[1:]] == [row["url"] for row in inventory.queues]
    assert metadata["queues"] == {row["name"]: 16 for row in inventory.queues}


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_arn",
        "wrong_account",
        "wrong_name",
        "fifo_arn",
        "fifo_flag",
        "kms",
        "missing_created",
        "invalid_created",
        "old_created",
        "missing_size",
        "zero_size",
        "oversize",
        "missing_attributes",
    ],
)
def test_queue_metadata_gaps_and_unpriced_shapes_never_issue_a_permit(budget, mutation):
    service, clients, _ = monitor(budget)

    def send(request):
        body = json.loads(request.body)
        assert body["AttributeNames"] == QUEUE_ATTRIBUTES
        result = attributes(body["QueueUrl"], service.inventory.value["metering_started_at"])
        if mutation == "missing_arn":
            del result["QueueArn"]
        elif mutation == "wrong_account":
            result["QueueArn"] = result["QueueArn"].replace("123456789012", "999999999999")
        elif mutation == "wrong_name":
            result["QueueArn"] += "-other"
        elif mutation == "fifo_arn":
            result["QueueArn"] += ".fifo"
        elif mutation == "fifo_flag":
            result["FifoQueue"] = "true"
        elif mutation == "kms":
            result["KmsMasterKeyId"] = "synthetic-kms-key"
        elif mutation == "missing_created":
            del result["CreatedTimestamp"]
        elif mutation == "invalid_created":
            result["CreatedTimestamp"] = "unknown"
        elif mutation == "old_created":
            result["CreatedTimestamp"] = str(service.inventory.value["metering_started_at"] - 901)
        elif mutation == "missing_size":
            del result["MaximumMessageSize"]
        else:
            result["MaximumMessageSize"] = "0" if mutation == "zero_size" else "1048577"
        return wire_response(request, 200, {} if mutation == "missing_attributes" else {"Attributes": result})

    with closing(sqs_client()) as client, patch.object(client._endpoint.http_session, "send", side_effect=send):
        service.telemetry.sqs = client
        with pytest.raises(UnverifiedCost):
            service.run()
    record = service.state.read(service.state.budget.month(), "AWS")
    assert record["measurement_state"] == "UNVERIFIED" and record["covered_until"] == 0
    with pytest.raises(MemoryBudgetPaused):
        service.state.budget.reserve("unverified-queue", purpose="extract")
    clients.cloudwatch.get_metric_data.assert_not_called()
    clients.logs.start_query.assert_not_called()


@pytest.mark.parametrize("error", ["InvalidAttributeName", "AccessDenied", "QueueDoesNotExist", "RequestThrottled"])
def test_queue_errors_still_pause_and_are_not_retried_as_partial_metadata(budget, error):
    service, clients, _ = monitor(budget)
    calls = []

    def send(request):
        body = json.loads(request.body)
        assert body["AttributeNames"] == QUEUE_ATTRIBUTES
        calls.append(body)
        return wire_response(request, 400, {"__type": error, "message": "Synthetic service error"})

    with closing(sqs_client()) as client, patch.object(client._endpoint.http_session, "send", side_effect=send):
        service.telemetry.sqs = client
        with pytest.raises(UnverifiedCost):
            service.run()
    assert len(calls) == 1
    record = service.state.read(service.state.budget.month(), "AWS")
    assert record["measurement_state"] == "UNVERIFIED" and record["covered_until"] == 0
    with pytest.raises(MemoryBudgetPaused):
        service.state.budget.reserve("queue-error", purpose="answer")
    clients.cloudwatch.get_metric_data.assert_not_called()
