import importlib
import os
import sys
import types

from zerde_common import secrets


class _FakeSSMClient:
    def __init__(self, parameters: list[dict[str, str]], invalid: list[str]) -> None:
        self._parameters = parameters
        self._invalid = invalid

    def get_parameters(self, *, Names: list[str], WithDecryption: bool) -> dict[str, object]:
        return {"Parameters": self._parameters, "InvalidParameters": self._invalid}


def test_optional_ssm_parameters_do_not_raise(monkeypatch):
    monkeypatch.setattr(secrets, "_loaded_env_keys_by_prefix", {})
    monkeypatch.delenv("OPTIONAL_API_KEY", raising=False)

    fake_boto3 = types.SimpleNamespace(
        client=lambda service_name: _FakeSSMClient(parameters=[], invalid=["/app/prod/optional-api-key"])
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    secrets.load_ssm_secrets_if_needed(
        "/app/prod",
        {"optional-api-key": "OPTIONAL_API_KEY"},
        required=False,
    )

    assert os.environ.get("OPTIONAL_API_KEY") is None


def test_bot_config_imports_when_optional_ssm_ai_key_is_missing(monkeypatch):
    monkeypatch.setattr(secrets, "_loaded_env_keys_by_prefix", {})
    monkeypatch.setenv("SSM_SECRET_PREFIX", "/zerde/test")
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("WEBHOOK_SECRET_TOKEN", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    fake_boto3 = types.SimpleNamespace(
        client=lambda service_name: _FakeSSMClient(
            parameters=[
                {"Name": "/zerde/test/bot-token", "Value": "bot-token"},
                {"Name": "/zerde/test/webhook-secret-token", "Value": "webhook-secret"},
            ],
            invalid=[],
        )
    )
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    sys.modules.pop("core.config", None)

    config = importlib.import_module("core.config")

    assert config.get_bot_token() == "bot-token"
    assert config.get_groq_api_key() is None
