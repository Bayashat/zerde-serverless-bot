"""Invalid local admission must not become a provider retry or failover."""

import json
from decimal import Decimal
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from services.ai import gemini_client
from services.repositories import rate_limit

from tests import test_explicit_provider_fences as fences

env = fences.env


def ready(env, monkeypatch):
    values = fences.setup(env, monkeypatch, media=False)
    http, providers = values[-2:]
    http.request.return_value = Mock(
        status=200, data=json.dumps({"candidates": [{"content": {"parts": [{"text": "Synthetic answer"}]}}]}).encode()
    )
    for provider in providers:
        provider._http.request.return_value = Mock(
            status=200, data=b'{"choices":[{"message":{"content":"Synthetic fallback"}}]}'
        )
    return values


def rejected(delivery, overlay):
    with pytest.raises(RuntimeError, match="^Gemini quota admission unavailable$") as raised:
        fences.answer(delivery, overlay)
    assert type(raised.value).__name__ == "GeminiQuotaUnavailableError"
    assert not isinstance(raised.value, (gemini_client.GeminiUnavailableError, gemini_client.GeminiRPDExhaustedError))


def test_real_counter_client_error_cannot_authorize_http(env, monkeypatch):
    _, delivery, api, overlay, gemini, http, providers = ready(env, monkeypatch)
    table = Mock()
    table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "synthetic"}}, "UpdateItem"
    )
    db = Mock()
    db.Table.return_value = table
    monkeypatch.setattr(rate_limit, "get_dynamodb", lambda: db)
    gemini._rate_repo = rate_limit.RateLimitRepository()
    try:
        rejected(delivery, overlay)
    finally:
        delivery.close()
    table.update_item.assert_called_once()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent


@pytest.mark.parametrize(
    "result",
    [
        (0, True),
        (-1, True),
        (True, True),
        (1.0, True),
        (Decimal(1), True),
        ("1", True),
        (1, 1),
        (1, "yes"),
        (1, None),
        None,
        (),
        (1,),
        (1, True, "extra"),
    ],
)
def test_invalid_admission_return_never_retries_or_falls_back(env, monkeypatch, result):
    _, delivery, api, overlay, gemini, http, providers = ready(env, monkeypatch)
    gemini._rate_repo.increment_and_check.return_value = result
    try:
        rejected(delivery, overlay)
    finally:
        delivery.close()
    gemini._rate_repo.increment_and_check.assert_called_once()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent


def test_invalid_second_admission_keeps_only_first_real_attempt(env, monkeypatch):
    _, delivery, api, overlay, gemini, http, providers = ready(env, monkeypatch)
    gemini._rate_repo.increment_and_check.side_effect = [(1, True), (0, True)]
    http.request.return_value = Mock(status=503, data=b"{}")
    try:
        rejected(delivery, overlay)
    finally:
        delivery.close()
    assert gemini._rate_repo.increment_and_check.call_count == 2
    http.request.assert_called_once()
    assert all(not item._http.request.called for item in providers) and not api.sent


def test_owner_exception_is_not_misclassified_as_provider_failure(env, monkeypatch):
    _, delivery, api, overlay, gemini, http, providers = ready(env, monkeypatch)
    error = ValueError("synthetic owner failure")
    gemini._rate_repo.increment_and_check.side_effect = error
    try:
        with pytest.raises(ValueError) as raised:
            fences.answer(delivery, overlay)
        assert raised.value is error
    finally:
        delivery.close()
    gemini._rate_repo.increment_and_check.assert_called_once()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent


@pytest.mark.parametrize("exhausted", [False, True])
def test_valid_admission_keeps_success_and_exhaustion_paths(env, monkeypatch, exhausted):
    _, delivery, api, overlay, gemini, http, providers = ready(env, monkeypatch)
    gemini._rate_repo.increment_and_check.return_value = (101, False) if exhausted else (1, True)
    try:
        assert fences.answer(delivery, overlay)
    finally:
        delivery.close()
    gemini._rate_repo.increment_and_check.assert_called_once()
    assert http.request.call_count == (0 if exhausted else 1)
    assert providers[0]._http.request.call_count == (1 if exhausted else 0)
    assert not providers[1]._http.request.called and len(api.sent) == 1
