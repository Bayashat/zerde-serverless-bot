"""Local storage/provider simulations, not live quota or billing evidence."""

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from threading import Barrier, Lock
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from services.memory_v2.answer_selector import AnswerSelectionUnavailable, MemoryAnswerSelector
from services.repositories import rate_limit
from zerde_common.logger import JSONFormatter

from tests import test_explicit_quota_guard as explicit
from tests import test_memory_answer_budget as answers
from tests import test_memory_v2_extraction as extraction

KEY = {"stat_key": "RATE#gemini_generate#2026-03-07"}
env = explicit.env


@pytest.fixture
def counter(monkeypatch):
    with mock_aws():
        db = boto3.resource(
            "dynamodb", region_name="eu-central-1", aws_access_key_id="fake", aws_secret_access_key="fake"
        )
        table = db.create_table(
            TableName=rate_limit.STATS_TABLE_NAME,
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: db)
        repo = rate_limit.RateLimitRepository(rpd_limit=5)
        monkeypatch.setattr(repo, "_today_pt", lambda: "2026-03-07")
        yield repo, table


@pytest.mark.parametrize(
    "attrs",
    [{}, {"request_count": -1}, {"request_count": Decimal("0.5")}, {"request_count": True}, {"request_count": "1"}],
)
def test_bad_stored_counter_and_ttl_are_preserved_without_a_permit(counter, attrs):
    repo, table = counter
    table.put_item(Item={**KEY, **attrs, "ttl": 123, "other": "keep"})
    before = table.get_item(Key=KEY, ConsistentRead=True)["Item"]
    assert repo.increment_and_check() == (0, True)
    assert table.get_item(Key=KEY, ConsistentRead=True)["Item"] == before


def mock_counter(monkeypatch, response=None, *, limit=5):
    table = Mock()
    table.get_item.return_value = {} if response is None else response
    db = Mock()
    db.Table.return_value = table
    monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: db)
    repo = rate_limit.RateLimitRepository(rpd_limit=limit)
    monkeypatch.setattr(repo, "_today_pt", lambda: "2026-03-07")
    return repo, table


def conditional(metadata):
    error = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "synthetic"}},
        "UpdateItem",
    )
    error.response["ResponseMetadata"] = metadata
    return error


def test_missing_day_and_valid_decimal_keep_ttl_scope_and_exhaustion(counter):
    repo, table = counter
    assert repo.increment_and_check() == (1, True)
    first = table.get_item(Key=KEY)["Item"]
    # Existing 48h wall-clock delta crosses the March DST transition: 47 elapsed hours.
    assert first["ttl"] == int(datetime(2026, 3, 9, 7, tzinfo=timezone.utc).timestamp())
    table.put_item(Item={**KEY, "request_count": Decimal(4), "ttl": 123, "other": "keep"})
    assert repo.increment_and_check() == (5, True)
    assert repo.increment_and_check() == (6, False)
    last = table.get_item(Key=KEY)["Item"]
    assert last["request_count"] == 6 and last["other"] == "keep" and last["ttl"] == first["ttl"]
    repo._today_pt = lambda: "2026-03-08"
    assert repo.increment_and_check() == (1, True)
    assert table.get_item(Key=KEY)["Item"] == last
    scoped = rate_limit.RateLimitRepository(scope="synthetic_scope", rpd_limit=0)
    scoped._today_pt = lambda: "2026-03-07"
    assert scoped.increment_and_check() == (1, False)
    assert scoped.increment_and_check(scope="separate_override") == (1, True)
    assert table.get_item(Key={"stat_key": "RATE#synthetic_scope#2026-03-07"})["Item"]["request_count"] == 1
    assert table.get_item(Key={"stat_key": "RATE#separate_override#2026-03-07"})["Item"]["request_count"] == 1


@pytest.mark.parametrize("value", [0, 2, Decimal(0), Decimal("2.00")])
def test_strict_valid_numbers_are_returned_as_true_int(counter, value):
    repo, table = counter
    table.put_item(Item={**KEY, "request_count": value})
    count, allowed = repo.increment_and_check()
    assert type(count) is int and count == value + 1 and allowed is True


@pytest.mark.parametrize(
    "value", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"), Decimal("-Infinity"), 1.5, None]
)
def test_unstorable_counter_values_are_local_negative_controls(monkeypatch, value):
    repo, table = mock_counter(monkeypatch, {"Item": {**KEY, "request_count": value}})
    assert repo.increment_and_check() == (0, True)
    table.update_item.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [[], "bad", {"Item": None}, {"Item": {}}, {"Item": []}, {"Item": {"stat_key": "wrong", "request_count": 1}}],
)
def test_malformed_reads_are_not_missing_items(monkeypatch, response):
    repo, table = mock_counter(monkeypatch, response)
    assert repo.increment_and_check() == (0, True)
    table.update_item.assert_not_called()


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        None,
        [],
        {"RetryAttempts": None},
        {"RetryAttempts": True},
        {"RetryAttempts": False},
        {"RetryAttempts": 1},
        {"RetryAttempts": -1},
        {"RetryAttempts": 0.0},
        {"RetryAttempts": "0"},
    ],
)
def test_unconfirmed_conditional_errors_never_repeat_a_write(monkeypatch, metadata):
    repo, table = mock_counter(monkeypatch)
    table.update_item.side_effect = conditional(metadata)
    assert repo.increment_and_check() == (0, True)
    table.get_item.assert_called_once_with(Key=KEY, ConsistentRead=True)
    table.update_item.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"Error": None, "ResponseMetadata": {"RetryAttempts": 0}},
        {"Error": "bad", "ResponseMetadata": {"RetryAttempts": 0}},
        {"Error": {"Code": "Other"}, "ResponseMetadata": {"RetryAttempts": 0}},
        None,
    ],
)
def test_malformed_error_envelopes_do_not_enable_retry(monkeypatch, response):
    repo, table = mock_counter(monkeypatch)
    error = conditional({"RetryAttempts": 0})
    error.response = response
    table.update_item.side_effect = error
    assert repo.increment_and_check() == (0, True)
    assert table.get_item.call_count == table.update_item.call_count == 1


def test_confirmed_contention_is_bounded_to_three_rounds(monkeypatch):
    repo, table = mock_counter(monkeypatch)
    table.update_item.side_effect = conditional({"RetryAttempts": 0})
    assert repo.increment_and_check() == (0, True)
    assert table.get_item.call_count == table.update_item.call_count == 3


def test_known_conflict_rereads_before_authorizing(monkeypatch):
    repo, table = mock_counter(monkeypatch)
    table.get_item.side_effect = [{}, {"Item": {**KEY, "request_count": Decimal(1)}}]
    table.update_item.side_effect = [conditional({"RetryAttempts": 0}), {"Attributes": {"request_count": Decimal(2)}}]
    assert repo.increment_and_check() == (2, True)
    assert table.get_item.call_count == table.update_item.call_count == 2
    assert table.update_item.call_args_list[0].kwargs["ConditionExpression"] == "attribute_not_exists(stat_key)"
    assert table.update_item.call_args_list[1].kwargs["ExpressionAttributeValues"][":previous"] == 1


def test_two_callers_cannot_both_take_the_last_permit(counter, monkeypatch):
    repo, table = counter
    table.put_item(Item={**KEY, "request_count": Decimal(4)})
    barrier, lock, reads = Barrier(2), Lock(), []

    class CoordinatedTable:
        def get_item(self, **kwargs):
            assert kwargs["ConsistentRead"] is True
            with lock:
                response = table.get_item(**kwargs)
                reads.append(1)
                synchronize = len(reads) <= 2
            if synchronize:
                barrier.wait(timeout=5)
            return response

        def update_item(self, **kwargs):
            # Serialize the service's atomic condition/update boundary, not the callers' reads.
            with lock:
                return table.update_item(**kwargs)

    monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: Mock(Table=Mock(return_value=CoordinatedTable())))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: repo.increment_and_check(), range(2)))
    assert sorted(results) == [(5, True), (6, False)]
    assert table.get_item(Key=KEY)["Item"]["request_count"] == 6


@pytest.mark.parametrize("failure", ["sdk_retried_conflict", "malformed_success", "timeout"])
def test_unknown_after_real_local_write_retains_increment_without_replay(counter, monkeypatch, failure):
    repo, table = counter
    wrapped = Mock(wraps=table)
    error = TimeoutError("synthetic transport")

    def after_write(**kwargs):
        table.update_item(**kwargs)
        if failure == "sdk_retried_conflict":
            raise conditional({"RetryAttempts": 1})
        if failure == "timeout":
            raise error
        return {"Attributes": {"request_count": True}}

    wrapped.update_item.side_effect = after_write
    monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: Mock(Table=Mock(return_value=wrapped)))
    if failure == "timeout":
        with pytest.raises(TimeoutError) as caught:
            repo.increment_and_check()
        assert caught.value is error
    else:
        assert repo.increment_and_check() == (0, True)
    assert wrapped.get_item.call_count == wrapped.update_item.call_count == 1
    assert table.get_item(Key=KEY)["Item"]["request_count"] == 1


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"Attributes": None},
        {"Attributes": {}},
        {"Attributes": {"request_count": True}},
        {"Attributes": {"request_count": 1.0}},
        {"Attributes": {"request_count": Decimal("1.5")}},
        {"Attributes": {"request_count": Decimal("NaN")}},
        {"Attributes": {"request_count": 2}},
    ],
)
def test_untrusted_success_never_grants_or_retries(monkeypatch, response):
    repo, table = mock_counter(monkeypatch)
    table.update_item.return_value = response
    assert repo.increment_and_check() == (0, True)
    assert table.get_item.call_count == table.update_item.call_count == 1


@pytest.mark.parametrize("phase", ["get_item", "update_item"])
@pytest.mark.parametrize("client_error", [True, False])
def test_storage_failure_is_unavailable_or_original_exception(monkeypatch, phase, client_error):
    repo, table = mock_counter(monkeypatch)
    error = (
        ClientError({"Error": {"Code": "AccessDeniedException"}}, phase) if client_error else ValueError("synthetic")
    )
    getattr(table, phase).side_effect = error
    if client_error:
        assert repo.increment_and_check() == (0, True)
    else:
        with pytest.raises(ValueError) as caught:
            repo.increment_and_check()
        assert caught.value is error
    assert table.get_item.call_count == 1
    assert table.update_item.call_count == (phase == "update_item")


@pytest.mark.parametrize("client_error", [True, False])
def test_resource_acquisition_keeps_existing_error_boundary(monkeypatch, client_error):
    repo = rate_limit.RateLimitRepository()
    error = ClientError({"Error": {"Code": "Denied"}}, "synthetic") if client_error else TimeoutError("synthetic")
    monkeypatch.setattr(rate_limit, "get_dynamodb", Mock(side_effect=error))
    if client_error:
        assert repo.increment_and_check() == (0, True)
    else:
        with pytest.raises(TimeoutError) as caught:
            repo.increment_and_check()
        assert caught.value is error


def test_row_corrupted_after_read_is_not_overwritten(counter, monkeypatch):
    repo, table = counter
    table.put_item(Item={**KEY, "request_count": 4, "ttl": 123})
    wrapped = Mock(wraps=table)
    corrupted = {**KEY, "request_count": "synthetic bad count", "ttl": 777}

    def read_then_corrupt(**kwargs):
        result = table.get_item(**kwargs)
        table.put_item(Item=corrupted)
        return result

    wrapped.get_item.side_effect = read_then_corrupt
    monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: Mock(Table=Mock(return_value=wrapped)))
    assert repo.increment_and_check() == (0, True)
    assert wrapped.get_item.call_count == 2 and wrapped.update_item.call_count == 1
    assert table.get_item(Key=KEY)["Item"] == corrupted


@pytest.mark.parametrize("exhausted", [False, True])
def test_real_writer_keeps_explicit_success_and_legal_exhaustion(env, monkeypatch, exhausted):
    _, delivery, api, overlay, gemini, http, providers = explicit.ready(env, monkeypatch)
    gemini._rate_repo, table = mock_counter(monkeypatch, limit=0 if exhausted else 5)
    table.update_item.return_value = {"Attributes": {"request_count": Decimal(1)}}
    try:
        assert explicit.fences.answer(delivery, overlay)
    finally:
        delivery.close()
    assert table.get_item.call_count == table.update_item.call_count == 1
    assert http.request.call_count == (0 if exhausted else 1)
    assert providers[0]._http.request.call_count == (1 if exhausted else 0)
    assert not providers[1]._http.request.called and len(api.sent) == 1


def configured_failure(monkeypatch, mode):
    repo, table = mock_counter(monkeypatch)
    if mode == "bad_row":
        table.get_item.return_value = {"Item": {**KEY, "request_count": Decimal("0.5")}}
    elif mode == "read_error":
        table.get_item.side_effect = ClientError({"Error": {"Code": "AccessDeniedException"}}, "GetItem")
    elif mode == "unknown_write":
        table.update_item.side_effect = conditional({"RetryAttempts": 1})
    else:
        table.update_item.side_effect = TimeoutError("synthetic owner timeout")
    return repo, table


@pytest.mark.parametrize("mode", ["bad_row", "read_error", "unknown_write", "timeout"])
def test_actual_writer_stops_explicit_dispatch_before_http_or_fallback(env, monkeypatch, mode):
    _, delivery, api, overlay, gemini, http, providers = explicit.ready(env, monkeypatch)
    gemini._rate_repo, table = configured_failure(monkeypatch, mode)
    try:
        if mode == "timeout":
            with pytest.raises(TimeoutError) as caught:
                explicit.fences.answer(delivery, overlay)
            assert caught.value is table.update_item.side_effect
        else:
            explicit.rejected(delivery, overlay)
    finally:
        delivery.close()
    assert not http.request.called and all(not item._http.request.called for item in providers) and not api.sent
    assert table.get_item.call_count == 1 and table.update_item.call_count <= 1


@pytest.mark.parametrize("mode", ["bad_row", "read_error", "unknown_write", "timeout"])
def test_actual_writer_stops_both_memory_consumers_before_reservation(monkeypatch, mode):
    repo, table = configured_failure(monkeypatch, mode)
    instance, provider, budget, _, _ = extraction.extractor()
    instance.rate_limit = repo
    result = asyncio.run(instance.extract_batch([extraction.source()]))
    assert result[0].status == "defer" and result[0].reason == "daily_quota_unavailable"
    provider.generate.assert_not_called()
    budget.reserve.assert_not_called()
    budget.settle.assert_not_called()
    table.reset_mock()
    budget = Mock()
    provider = answers.Provider([])
    selector = MemoryAnswerSelector(provider, budget, validate_snapshot=answers.valid, rate_limit=repo)
    with pytest.raises(AnswerSelectionUnavailable):
        answers.run(selector)
    assert provider.calls == 0 and table.get_item.call_count == 1 and table.update_item.call_count <= 1
    budget.reserve.assert_not_called()
    budget.settle.assert_not_called()


def test_diagnostic_is_fixed_json_without_raw_values_or_exception_chains(monkeypatch):
    canary = "SYNTHETIC_PRIVATE_CONTENT_7Q9"
    repo, table = mock_counter(monkeypatch, {"Item": {**KEY, "request_count": canary}})
    stream, diagnostic = StringIO(), logging.Logger("shared-writer-synthetic")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    diagnostic.addHandler(handler)
    monkeypatch.setattr(rate_limit, "logger", rate_limit.LoggerAdapter(diagnostic, {}))
    assert repo.increment_and_check() == (0, True)
    table.get_item.return_value = {}
    error = ClientError({"Error": {"Code": "AccessDeniedException", "Message": canary}}, "UpdateItem")
    error.__cause__, error.__context__ = ValueError(canary), ValueError(canary)
    table.update_item.side_effect = error
    assert repo.increment_and_check() == (0, True)
    raw = stream.getvalue()
    lines = [json.loads(line) for line in raw.splitlines()]
    assert len(lines) == 2 and canary not in raw
    assert {line["reason"] for line in lines} == {"invalid_count", "write_error"}
    assert all(line["message"] == "Gemini quota admission unavailable" for line in lines)
    failure = RuntimeError("synthetic logger failed")
    monkeypatch.setattr(rate_limit, "logger", Mock(warning=Mock(side_effect=failure)))
    with pytest.raises(RuntimeError) as caught:
        repo.increment_and_check()
    assert caught.value is failure
