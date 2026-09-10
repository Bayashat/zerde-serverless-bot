"""Real provider dispatch with Moto source revocation and synthetic HTTP replies."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from services import group_agent
from services.ai import gemini_client, group_chat_reply_fallback
from services.ai.gemini_client import GeminiClient
from services.ai.group_chat_reply_fallback import (
    FallbackGroupChatReplyProvider,
    OpenAICompatibleGroupChatReplyProvider,
)
from services.memory_v2.media_ephemeral import EphemeralMediaRepository
from services.memory_v2.models import MemoryUnavailable

from tests import test_memory_v2_contract as contract
from tests.test_ephemeral_media import store
from tests.test_explicit_delivery import body, guard
from tests.test_memory_public_runtime import API
from tests.test_memory_v2_contract import CHAT, activate, event

env = contract.env


def setup(env, monkeypatch, *, media=True):
    activate(env)
    overlay = Mock()
    if media:
        source, _ = store(env)
        media_repo = EphemeralMediaRepository(env.repo)
        overlay.get_media_group_refs.side_effect = media_repo.get_refs
        request = body(env, refs=media_repo.get_refs(CHAT, "album-1"))
    else:
        source = event(env, "90", text="Explain SQL")
        env.repo.observe(source)
        request = body(env)
    api = API()
    delivery = guard(env, request, api, overlay)
    delivery.start()
    gemini = GeminiClient.__new__(GeminiClient)
    gemini._api_key, gemini._model = "synthetic-key", "synthetic-model"
    gemini._rate_repo = Mock(rpd_limit=100)
    gemini._rate_repo.increment_and_check.return_value = (1, True)
    providers = [
        OpenAICompatibleGroupChatReplyProvider(name, "synthetic-key", "https://invalid", "model")
        for name in ("deepseek", "groq")
    ]
    for provider in providers:
        provider._http = Mock()
    http = Mock()
    monkeypatch.setattr(gemini_client, "_http", http)
    monkeypatch.setattr(gemini_client, "_circuit_is_open", lambda: False)
    monkeypatch.setattr(group_agent, "_get_gemini", lambda: gemini)
    monkeypatch.setattr(
        group_agent, "_get_group_chat_reply_fallback", lambda: FallbackGroupChatReplyProvider(providers)
    )
    monkeypatch.setattr(group_agent, "_group_chat_reply_gemini_retry_delay", lambda _: 0)
    return source, delivery, api, overlay, gemini, http, providers


def answer(delivery, overlay):
    return group_agent.answer_group_question(
        repo=overlay,
        bot=delivery,
        chat_id=CHAT,
        reply_to_message_id=90,
        user_text="Explain this request",
        lang="en",
        media_parts=(
            [{"inline_data": {"mime_type": "image/jpeg", "data": "synthetic"}}] if delivery.media_refs else None
        ),
    )


@pytest.mark.parametrize("lane", ["gemini_retry", "gemini_to_fallback", "fallback_next"])
@pytest.mark.parametrize("media", [False, True])
def test_source_revocation_stops_every_provider_retry_or_failover(env, monkeypatch, lane, media):
    source, delivery, api, overlay, _, http, providers = setup(env, monkeypatch, media=media)

    def revoke(*args, **kwargs):
        env.clock.now += 1
        env.repo.observe(replace(source, edited_at=env.clock.now, text="changed"))
        return Mock(status=503, data=b"{}")

    if lane == "fallback_next":
        monkeypatch.setattr(group_agent, "_get_gemini", lambda: None)
        providers[0]._http.request.side_effect = revoke
    else:
        http.request.side_effect = revoke
        if lane == "gemini_to_fallback":
            monkeypatch.setattr(group_agent, "GROUP_CHAT_REPLY_GEMINI_MAX_ATTEMPTS", 1)
    with pytest.raises(MemoryUnavailable):
        answer(delivery, overlay)
    delivery.close()
    assert http.request.call_count == (0 if lane == "fallback_next" else 1)
    assert providers[0]._http.request.call_count == (1 if lane == "fallback_next" else 0)
    assert providers[1]._http.request.call_count == 0
    assert not api.sent


def test_gemini_http_boundary_rechecks_after_quota_database_latency(env, monkeypatch):
    source, delivery, api, overlay, gemini, http, providers = setup(env, monkeypatch)

    def quota():
        env.clock.now += 1
        env.repo.observe(replace(source, edited_at=env.clock.now, text="changed"))
        return 1, True

    gemini._rate_repo.increment_and_check.side_effect = quota
    with pytest.raises(MemoryUnavailable):
        answer(delivery, overlay)
    delivery.close()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent


def test_fallback_http_boundary_rechecks_after_prompt_preparation(env, monkeypatch):
    source, delivery, api, overlay, _, http, providers = setup(env, monkeypatch)
    monkeypatch.setattr(group_agent, "_get_gemini", lambda: None)
    original = group_chat_reply_fallback._build_group_chat_reply_prompts

    def build(**kwargs):
        result = original(**kwargs)
        env.clock.now += 1
        env.repo.observe(replace(source, edited_at=env.clock.now, text="changed"))
        return result

    monkeypatch.setattr(group_chat_reply_fallback, "_build_group_chat_reply_prompts", build)
    with pytest.raises(MemoryUnavailable):
        answer(delivery, overlay)
    delivery.close()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent


def test_source_fence_database_error_propagates_without_provider_fallback(env, monkeypatch):
    _, delivery, api, overlay, _, http, providers = setup(env, monkeypatch)
    original = env.repo.get_control
    failed = False

    def control(chat):
        nonlocal failed
        if not failed:
            failed = True
            raise ClientError({"Error": {"Code": "InternalServerError"}}, "GetItem")
        return original(chat)

    monkeypatch.setattr(env.repo, "get_control", control)
    with pytest.raises(ClientError):
        answer(delivery, overlay)
    delivery.close()
    assert not http.request.called and all(not item._http.request.called for item in providers)
    assert not api.sent
