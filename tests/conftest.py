import pytest


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_token")
    monkeypatch.setenv("WEBHOOK_SECRET_TOKEN", "test_secret")
    monkeypatch.setenv("QUEUE_URL", "test_queue")
    monkeypatch.setenv("STATS_TABLE_NAME", "test_stats_table")
