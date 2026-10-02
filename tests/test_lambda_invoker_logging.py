"""Sync invocation preserves its wire contract without logging response content."""

import io
import json
import logging
from unittest.mock import Mock

import pytest
from core.logger import LoggerAdapter
from services.repositories import lambda_invoker
from zerde_common.logger import JSONFormatter

PRIVATE = "private poll question Алматы 私人正文"
FAKE_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ_fake_token"
PAYLOAD = {"action": "reconcile", "poll_message": {"poll": {"question": PRIVATE}}, "nested": [1, None]}
FUNCTION = "quiz-test-function"


@pytest.fixture
def sync_logs(monkeypatch):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    sink = logging.Logger("sync-invoker-log-test", logging.DEBUG)
    sink.addHandler(handler)
    monkeypatch.setattr(lambda_invoker, "logger", LoggerAdapter(sink, {}))
    return output


def assert_single_request(invoker):
    invoker._client.invoke.assert_called_once_with(
        FunctionName=FUNCTION, InvocationType="RequestResponse", Payload=json.dumps(PAYLOAD).encode()
    )


def fail_with_content(chain):
    if chain == "direct":
        raise RuntimeError(f"{PRIVATE} {FAKE_TOKEN}")
    try:
        raise ValueError(f"{PRIVATE} {FAKE_TOKEN}")
    except ValueError as cause:
        if chain == "cause":
            raise RuntimeError(PRIVATE) from cause
        raise RuntimeError(PRIVATE)


@pytest.mark.parametrize("stage", ["invoke", "read"])
@pytest.mark.parametrize("chain", ["direct", "cause", "context"])
def test_sync_failure_omits_arbitrary_content_and_chain(stage, chain, sync_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    stream = Mock()
    invoker._client.invoke.return_value = {"Payload": stream}
    target = invoker._client.invoke if stage == "invoke" else stream.read
    target.side_effect = lambda **_: fail_with_content(chain)

    assert invoker.invoke(FUNCTION, PAYLOAD) == {}

    assert_single_request(invoker)
    if stage == "read":
        stream.read.assert_called_once_with()
    else:
        stream.read.assert_not_called()
    record = json.loads(sync_logs.getvalue())
    assert PRIVATE not in json.dumps(record, ensure_ascii=False)
    assert FAKE_TOKEN not in sync_logs.getvalue()
    assert set(record) == {"timestamp", "level", "message", "location", "function_name", "error_type"}
    assert record["message"] == "Lambda invocation failed"
    assert record["function_name"] == FUNCTION
    assert record["error_type"] == "RuntimeError"


@pytest.mark.parametrize(
    "raw,error_type",
    [(PRIVATE.encode(), "JSONDecodeError"), (b"\xff" + PRIVATE.encode(), "UnicodeDecodeError")],
)
def test_sync_decode_failure_preserves_empty_result_without_response_log(raw, error_type, sync_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    invoker._client.invoke.return_value = {"Payload": io.BytesIO(raw)}

    assert invoker.invoke(FUNCTION, PAYLOAD) == {}

    assert_single_request(invoker)
    record = json.loads(sync_logs.getvalue())
    assert set(record) == {"timestamp", "level", "message", "location", "function_name", "error_type"}
    assert record["message"] == "Lambda invocation failed"
    assert record["function_name"] == FUNCTION
    assert record["error_type"] == error_type


@pytest.mark.parametrize("result", [{"status": "ok"}, [PRIVATE], PRIVATE, 7, False, None])
def test_sync_returns_each_valid_json_value_unchanged(result, sync_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    invoker._client.invoke.return_value = {"Payload": io.BytesIO(json.dumps(result).encode())}

    actual = invoker.invoke(FUNCTION, PAYLOAD)

    assert actual == result and type(actual) is type(result)
    assert_single_request(invoker)
    assert sync_logs.getvalue() == ""


def test_sync_function_error_keeps_original_json_parsing(sync_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    response = {"errorMessage": PRIVATE, "errorType": "RuntimeError"}
    invoker._client.invoke.return_value = {
        "FunctionError": "Unhandled",
        "Payload": io.BytesIO(json.dumps(response).encode()),
    }

    assert invoker.invoke(FUNCTION, PAYLOAD) == response

    assert_single_request(invoker)
    assert sync_logs.getvalue() == ""


def test_sync_empty_response_keeps_empty_result(sync_logs):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    invoker._client.invoke.return_value = {"Payload": io.BytesIO(b"")}

    assert invoker.invoke(FUNCTION, PAYLOAD) == {}

    assert_single_request(invoker)
    assert sync_logs.getvalue() == ""


def test_sync_logger_failure_still_propagates(monkeypatch):
    invoker = lambda_invoker.LambdaInvoker()
    invoker._client = Mock()
    invoker._client.invoke.side_effect = RuntimeError(PRIVATE)
    logger_failure = OSError("synthetic broken log sink")
    sink = Mock()
    sink.error.side_effect = logger_failure
    monkeypatch.setattr(lambda_invoker, "logger", sink)

    with pytest.raises(OSError) as raised:
        invoker.invoke(FUNCTION, PAYLOAD)

    assert raised.value is logger_failure
    sink.error.assert_called_once()
    assert_single_request(invoker)
