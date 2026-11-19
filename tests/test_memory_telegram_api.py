import asyncio
import traceback

import httpx
import pytest
from services.memory_v2.models import MemoryUnavailable
from services.memory_v2.telegram_api import MemoryTelegramAPI, TelegramReadRetryRequired

TOKEN = "123456:synthetic-test-token"


def run(operation, handler):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await operation(MemoryTelegramAPI(TOKEN, client=client, configured=lambda _: True))

    return asyncio.run(execute())


def response(result):
    return httpx.Response(200, json={"ok": True, "result": result})


def test_exact_reply_destination_and_single_attempt():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.path.endswith("/sendMessage")
        return response({"message_id": 7, "chat": {"id": -100123}, "reply_to_message": {"message_id": 5}})

    assert run(lambda api: api.send(-100123, "safe", reply_to_message_id=5), handler) == 7
    assert len(requests) == 1


@pytest.mark.parametrize(
    "result",
    [
        {"message_id": 7, "chat": {"id": -100999}, "reply_to_message": {"message_id": 5}},
        {"message_id": True, "chat": {"id": -100123}, "reply_to_message": {"message_id": 5}},
        {"message_id": 7, "chat": {"id": -100123}},
    ],
)
def test_unknown_destination_is_not_success(result):
    with pytest.raises(MemoryUnavailable):
        run(lambda api: api.send(-100123, "safe", reply_to_message_id=5), lambda _: response(result))


@pytest.mark.parametrize("status,expected", [("creator", True), ("administrator", True), ("member", False)])
def test_admin_requires_exact_live_member(status, expected):
    assert (
        run(
            lambda api: api.authorize(-100123, 42, require_admin=True),
            lambda _: response({"user": {"id": 42}, "status": status}),
        )
        is expected
    )


def test_mismatched_identity_rejected():
    with pytest.raises(TelegramReadRetryRequired):
        run(lambda api: api.authorize(-100123, 42), lambda _: response({"user": {"id": 99}, "status": "administrator"}))


def test_exception_chain_never_contains_token_and_no_retry():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError(str(request.url), request=request)

    with pytest.raises(MemoryUnavailable) as caught:
        run(lambda api: api.send(-100123, "safe", reply_to_message_id=5), handler)
    assert TOKEN not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None and len(calls) == 1


def test_total_timeout_cancels_pending_transport(monkeypatch):
    from services.memory_v2 import telegram_api

    original_timeout = asyncio.timeout
    monkeypatch.setattr(telegram_api.asyncio, "timeout", lambda _: original_timeout(0.02))
    cancelled = []

    async def handler(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    with pytest.raises(MemoryUnavailable):
        run(lambda api: api.send(-100123, "safe", reply_to_message_id=5), handler)
    assert cancelled == [True]


@pytest.mark.parametrize("failure", ["transport", 500, 502, 503, 504])
@pytest.mark.parametrize("method", ["getChatMember", "getMe"])
def test_only_read_calls_can_recover_with_identical_payload(monkeypatch, failure, method):
    from services.memory_v2 import telegram_api

    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            if failure == "transport":
                raise httpx.TransportError("synthetic network detail " + TOKEN)
            return httpx.Response(failure, text="synthetic failure " + TOKEN)
        return response({"user": {"id": 42}, "status": "member"})

    assert run(lambda api: api.call(method, {"chat_id": "-100123", "user_id": "42"}), handler)["status"] == "member"
    assert len(requests) == 2 and requests[0].content == requests[1].content
    assert requests[0].url == requests[1].url


def test_read_retry_uses_original_payload_despite_caller_mutation(monkeypatch):
    from services.memory_v2 import telegram_api

    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    payload = {"chat_id": "-100123", "user_id": "42"}
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            payload["user_id"] = "99"
            return httpx.Response(503)
        return response({"user": {"id": 42}, "status": "member"})

    run(lambda api: api.call("getChatMember", payload), handler)
    assert len(requests) == 2 and requests[0].content == requests[1].content
    assert b'"user_id":"42"' in requests[1].content and payload["user_id"] == "99"


@pytest.mark.parametrize("failure", [400, 401, 403, 429, 302, "bad_json", "bad_shape", "wrong_identity"])
def test_denials_invalid_responses_and_identity_mismatch_do_not_retry(failure):
    requests = []

    def handler(request):
        requests.append(request)
        if type(failure) is int:
            return httpx.Response(failure, json={"ok": False, "parameters": {"retry_after": 1}})
        if failure == "bad_json":
            return httpx.Response(200, text="invalid")
        if failure == "bad_shape":
            return httpx.Response(200, json={"ok": 1, "result": {}})
        return response({"user": {"id": 99}, "status": "member"})

    with pytest.raises(TelegramReadRetryRequired):
        run(lambda api: api.authorize(-100123, 42), handler)
    assert len(requests) == 1


def test_failed_second_read_stops_and_http_trace_logs_and_exception_have_no_token(monkeypatch, caplog):
    import logging

    from services.memory_v2 import telegram_api

    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    calls = []

    def handler(request):
        calls.append(request)
        logging.getLogger("httpcore.http11").debug("trace %s", request.url)
        return httpx.Response(503, text=TOKEN)

    with caplog.at_level(logging.DEBUG), pytest.raises(TelegramReadRetryRequired) as caught:
        run(lambda api: api.authorize(-100123, 42), handler)
    assert len(calls) == 2
    assert TOKEN not in caplog.text and TOKEN not in str([r.__dict__ for r in caplog.records])
    assert TOKEN not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None
    failure = next(r for r in caplog.records if getattr(r, "reason", None) == "HTTP_REJECTED")
    assert failure.attempts == 2


def test_read_total_deadline_does_not_restart_and_cancels_second_attempt(monkeypatch):
    from services.memory_v2 import telegram_api

    monkeypatch.setattr(telegram_api, "_LOOKUP_DEADLINE", 0.04)
    monkeypatch.setattr(telegram_api, "_READ_ATTEMPT_DEADLINE", 0.03)
    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    attempts, cancelled = [], []

    async def handler(request):
        attempts.append(request)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    import time

    started = time.monotonic()
    with pytest.raises(TelegramReadRetryRequired):
        run(lambda api: api.authorize(-100123, 42), handler)
    assert len(attempts) == 2 and len(cancelled) == 2
    assert time.monotonic() - started < 0.2


def test_explicit_task_cancellation_never_starts_another_attempt(monkeypatch):
    from services.memory_v2 import telegram_api

    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    attempts = []

    async def handler(request):
        attempts.append(request)
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(lambda api: api.authorize(-100123, 42), handler)
    assert len(attempts) == 1


def test_actual_shared_transport_folded_protocol_failure_recovers_read_only(monkeypatch):
    import json

    import httpcore
    from services.memory_v2 import telegram_api
    from zerde_common import async_http

    monkeypatch.setattr(telegram_api, "_READ_RETRY_DELAY", 0)
    streams, written = [], []
    body = json.dumps({"ok": True, "result": {"user": {"id": 42}, "status": "member"}}).encode()

    class Stream(httpcore.AsyncMockStream):
        async def write(self, data, timeout=None):
            written.append(data)
            await super().write(data, timeout)

    class Backend(httpcore.AsyncNetworkBackend):
        async def connect_tcp(self, *args, **kwargs):
            # A malformed first HTTP response exercises the actual HTTPcore ->
            # shared TransportError translation, not a mocked high-level error.
            raw = (
                b"INVALID\r\n\r\n"
                if not streams
                else b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
            )
            stream = Stream([raw])
            streams.append(stream)
            return stream

    async def resolver(*args):
        return ["192.0.2.1"]

    factory = async_http.bounded_async_client
    backend = Backend()
    monkeypatch.setattr(
        async_http, "bounded_async_client", lambda **kw: factory(**kw, resolver=resolver, network_backend=backend)
    )
    assert asyncio.run(MemoryTelegramAPI(TOKEN, configured=lambda _: True).authorize(-100123, 42)) is True
    assert len(streams) == 2
    assert b"getChatMember" in b"".join(written)
