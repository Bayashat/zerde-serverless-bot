import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("setup_webhook", Path(__file__).parents[1] / "scripts/setup_webhook.py")
webhook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webhook)


def test_existing_subscription_and_delivery_settings_are_preserved():
    before = {
        "url": "https://example.test/webhook",
        "max_connections": 12,
        "allowed_updates": ["message", "callback_query", "poll_answer", "chat_member"],
    }
    after = {**before, "allowed_updates": [*before["allowed_updates"], "edited_message"], "pending_update_count": 3}
    call = Mock(side_effect=[before, True, after])
    assert webhook.configure_webhook("fake-token", "fake-secret", before["url"], call=call)["verified"]
    payload = call.call_args_list[1].args[2]
    assert payload["drop_pending_updates"] is False
    assert payload["max_connections"] == 12
    assert payload["secret_token"] == "fake-secret"
    assert set(payload["allowed_updates"]) == set(after["allowed_updates"])


def test_default_all_subscription_is_not_narrowed():
    before = {"url": "", "allowed_updates": []}
    after = {"url": "https://example.test/webhook", "allowed_updates": [], "max_connections": 40}
    call = Mock(side_effect=[before, True, after])
    webhook.configure_webhook("fake-token", "fake-secret", after["url"], call=call)
    assert call.call_args_list[1].args[2]["allowed_updates"] == []


def test_readback_mismatch_is_failure_without_second_write():
    call = Mock(side_effect=[{"allowed_updates": ["message"]}, True, {"url": "https://wrong.test"}])
    with pytest.raises(webhook.WebhookSetupError, match="readback"):
        webhook.configure_webhook("fake-token", "fake-secret", "https://example.test", call=call)
    assert [c.args[1] for c in call.call_args_list].count("setWebhook") == 1


def test_transport_error_does_not_expose_credential_or_retry(monkeypatch):
    opener = Mock(side_effect=OSError("https://api.telegram.org/botFAKE_SECRET_TOKEN/setWebhook"))
    monkeypatch.setattr(webhook, "urlopen", opener)
    with pytest.raises(webhook.WebhookSetupError) as caught:
        webhook.telegram_call("FAKE_SECRET_TOKEN", "setWebhook", {"secret_token": "FAKE_WEBHOOK_SECRET"})
    assert "FAKE_SECRET" not in str(caught.value)
    assert "FAKE_WEBHOOK" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert opener.call_count == 1


def test_existing_webhook_cannot_be_moved_to_a_different_environment():
    call = Mock(return_value={"url": "https://prod.example.test/webhook"})
    with pytest.raises(webhook.WebhookSetupError, match="URL differs"):
        webhook.configure_webhook("fake-token", "fake-secret", "https://dev.example.test/webhook", call=call)
    assert call.call_count == 1
