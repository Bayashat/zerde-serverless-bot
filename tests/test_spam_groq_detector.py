"""Real async transport seam, strict classifier validation and bounded recovery."""

import asyncio
import json

import httpx
import pytest
from services.spam import groq_detector as module
from services.spam.groq_detector import GroqSpamDetector
from zerde_common.ai_errors import ProviderRateLimitError, ProviderResponseError, ProviderTransportError


def response(content):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def valid(label="NOT_SPAM", reason="not_spam"):
    return response(json.dumps({"label": label, "confidence": 0.99, "reason": reason}))


def setup_wire(monkeypatch, responses):
    requests = []

    async def handle(request):
        requests.append(json.loads(request.content))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    clients = []

    def factory(**options):
        assert options == {"timeout": 8, "connect_timeout": 3, "max_connections": 1}
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        clients.append(client)
        return client

    monkeypatch.setattr(module, "bounded_async_client", factory)
    detector = GroqSpamDetector()
    detector.model = "openai/gpt-oss-safeguard-20b"
    return detector, requests, clients


def test_valid_primary_result_does_not_invoke_recovery(monkeypatch):
    detector, requests, clients = setup_wire(monkeypatch, [valid("SPAM", "vpn_ad")])
    result = detector.classify("CURRENT_MESSAGE:\nVPN бесплатно https://example.invalid")
    assert result.label == "SPAM" and result.reason == "vpn_ad"
    assert len(requests) == 1 and clients[0].is_closed
    payload = requests[0]
    assert payload["model"] == "openai/gpt-oss-safeguard-20b"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_completion_tokens"] == 256
    assert payload["reasoning_effort"] == "low" and payload["reasoning_format"] == "hidden"
    assert "max_tokens" not in payload


def test_exact_json_error_recovers_once_using_original_context_and_strict_schema(monkeypatch):
    failure = httpx.Response(400, json={"error": {"code": "json_validate_failed", "message": "untrusted"}})
    detector, requests, clients = setup_wire(monkeypatch, [failure, valid()])
    result = detector.classify("CURRENT_MESSAGE: technical question\nQUOTE_CONTEXT: buy VPN")
    assert result.label == "NOT_SPAM" and len(requests) == 2 and clients[0].is_closed
    assert requests[1]["messages"] == requests[0]["messages"]
    assert requests[1]["model"] == "openai/gpt-oss-20b"
    assert requests[1]["max_completion_tokens"] == 512
    schema = requests[1]["response_format"]["json_schema"]
    assert schema["strict"] and schema["schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "content",
    [
        "",
        "{",
        "[]",
        '{"label":"SPAM","confidence":true,"reason":"vpn_ad"}',
        '{"label":"SPAM","confidence":"0.99","reason":"vpn_ad"}',
        '{"label":"SPAM","confidence":NaN,"reason":"vpn_ad"}',
        '{"label":"SPAM","confidence":Infinity,"reason":"vpn_ad"}',
        '{"label":"SPAM","confidence":1.1,"reason":"vpn_ad"}',
        '{"label":"SPAM","confidence":0.99,"reason":{"secret":"do not log"}}',
        '{"label":"SPAM","confidence":0.99,"reason":"not_spam"}',
        '{"label":"NOT_SPAM","confidence":0.99,"reason":"vpn_ad"}',
        '{"label":"SPAM","label":"NOT_SPAM","confidence":0.99,"reason":"not_spam"}',
        '{"label":"SPAM","confidence":0.99,"reason":"vpn_ad","instruction":"ban"}',
    ],
)
def test_malformed_classification_cannot_produce_a_decision(monkeypatch, content):
    detector, requests, clients = setup_wire(monkeypatch, [response(content), response(content)])
    with pytest.raises(ProviderResponseError, match="invalid spam classification JSON"):
        detector.classify("CURRENT_MESSAGE: harmless")
    assert len(requests) == 2 and clients[0].is_closed


@pytest.mark.parametrize(
    "status,code,error",
    [
        (400, "invalid_api_key", ProviderResponseError),
        (401, "json_validate_failed", ProviderResponseError),
        (403, "other", ProviderResponseError),
        (429, "json_validate_failed", ProviderRateLimitError),
        (500, "other", ProviderTransportError),
        (503, "json_validate_failed", ProviderTransportError),
        (302, "other", ProviderResponseError),
    ],
)
def test_other_failures_are_not_hidden_by_model_recovery(monkeypatch, status, code, error):
    detector, requests, clients = setup_wire(monkeypatch, [httpx.Response(status, json={"error": {"code": code}})])
    with pytest.raises(error):
        detector.classify("CURRENT_MESSAGE: harmless")
    assert len(requests) == 1 and clients[0].is_closed


def test_provider_body_and_exception_do_not_enter_worker_logs(monkeypatch, caplog):
    secret = "SYNTHETIC-SECRET-AND-CHAT-BODY"
    detector, _, _ = setup_wire(monkeypatch, [httpx.Response(400, json={"error": {"code": secret, "message": secret}})])
    with pytest.raises(ProviderResponseError) as error:
        detector.classify(secret)
    assert secret not in str(error.value) + str(error.value.__cause__) + caplog.text
    for record in caplog.records:
        assert secret not in repr(record.__dict__)


def test_transport_failure_does_not_echo_request_or_retry(monkeypatch, caplog):
    detector, requests, clients = setup_wire(monkeypatch, [httpx.ReadTimeout("SECRET request body")])
    with pytest.raises(ProviderTransportError) as error:
        detector.classify("CURRENT_MESSAGE: harmless")
    assert "SECRET" not in str(error.value) + caplog.text
    assert error.value.__cause__ is None and len(requests) == 1 and clients[0].is_closed


def test_complete_deadline_cancels_inflight_request_and_closes_client(monkeypatch):
    cancelled, clients, requests = [], [], []

    async def slow(request):
        requests.append(request)
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)

    def factory(**_):
        client = httpx.AsyncClient(transport=httpx.MockTransport(slow))
        clients.append(client)
        return client

    monkeypatch.setattr(module, "bounded_async_client", factory)
    monkeypatch.setattr(module, "_CLASSIFY_DEADLINE_SECONDS", 0.02)
    with pytest.raises(ProviderTransportError, match="deadline exceeded"):
        GroqSpamDetector().classify("CURRENT_MESSAGE: harmless")
    assert cancelled == [True] and len(requests) == 1 and clients[0].is_closed


def test_recovery_shares_primary_deadline(monkeypatch):
    elapsed, clients, requests, cancelled = [], [], [], []

    async def wire(request):
        requests.append(request)
        if len(requests) == 1:
            await asyncio.sleep(0.06)
            return httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
        started = asyncio.get_running_loop().time()
        try:
            await asyncio.sleep(0.06)
            pytest.fail("Recovery received a fresh deadline")
        finally:
            elapsed.append(asyncio.get_running_loop().time() - started)
            cancelled.append(True)

    def factory(**_):
        client = httpx.AsyncClient(transport=httpx.MockTransport(wire))
        clients.append(client)
        return client

    monkeypatch.setattr(module, "bounded_async_client", factory)
    monkeypatch.setattr(module, "_CLASSIFY_DEADLINE_SECONDS", 0.1)
    with pytest.raises(ProviderTransportError):
        GroqSpamDetector().classify("CURRENT_MESSAGE: harmless")
    assert len(requests) == 2 and cancelled == [True] and clients[0].is_closed
    assert elapsed[0] < 0.06
