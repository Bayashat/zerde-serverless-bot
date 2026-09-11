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
