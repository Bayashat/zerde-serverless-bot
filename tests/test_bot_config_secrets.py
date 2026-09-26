import runpy
from pathlib import Path

import zerde_common.secrets as secrets


def test_retired_memory_settings_are_not_parsed_or_used(monkeypatch):
    monkeypatch.setenv("GROUP_MEMORY_RETENTION_DAYS", "3650")
    monkeypatch.setenv("GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS", "not-a-number")
    monkeypatch.setenv("MEMORY_TABLE_NAME", "retired-table")
    config = runpy.run_path(str(Path(__file__).parents[1] / "src/bot/core/config.py"))
    assert not any(name.startswith("GROUP_MEMORY_") for name in config)
    assert "MEMORY_TABLE_NAME" not in config


def test_bot_config_loads_only_the_requested_ssm_secret(monkeypatch):
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_load(prefix: str, names: dict[str, str]) -> None:
        calls.append((prefix, names))

    with monkeypatch.context() as scoped:
        scoped.setenv("SSM_SECRET_PREFIX", "/zerde/prod")
        scoped.delenv("GEMINI_API_KEY", raising=False)
        scoped.setattr(secrets, "load_ssm_secrets_if_needed", fake_load)

        config = runpy.run_path(str(Path(__file__).parents[1] / "src" / "bot" / "core" / "config.py"))
        assert calls == []

        assert config["get_gemini_api_key"]() is None
        assert calls == [("/zerde/prod", {"gemini-api-key": "GEMINI_API_KEY"})]
