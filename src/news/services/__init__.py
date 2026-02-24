"""Services for news lambda."""

import os


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


BOT_TOKEN: str = _require_env("BOT_TOKEN")

# NEWS_CHAT_ID supports comma-separated IDs: "-1001245,-1903430"
NEWS_CHAT_IDS: list[str] = [cid.strip() for cid in _require_env("NEWS_CHAT_IDS").split(",") if cid.strip()]
