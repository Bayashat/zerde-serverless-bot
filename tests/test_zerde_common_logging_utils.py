"""Tests for shared logging helpers."""

import json
import os
import sys

_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(_ROOT, "src", "shared", "python"))

from zerde_common.logging_utils import telegram_update_log_extra  # noqa: E402


def test_telegram_update_log_extra_inlines_small_update() -> None:
    update = {
        "update_id": 42,
        "message": {
            "message_id": 1,
            "text": "/start",
            "chat": {"id": -1001, "type": "supergroup"},
        },
    }
    extra = telegram_update_log_extra(update)
    assert extra["update_id"] == 42
    assert extra["telegram_update"] == update
    assert extra["telegram_update_truncated"] is False
    assert extra["telegram_update_chars"] == len(json.dumps(update, ensure_ascii=False))


def test_telegram_update_log_extra_truncates_huge_payload() -> None:
    long_text = "x" * 500_000
    update = {"update_id": 99, "message": {"text": long_text}}
    extra = telegram_update_log_extra(update, max_json_chars=10_000)
    assert extra["update_id"] == 99
    assert extra["telegram_update_truncated"] is True
    assert "telegram_update_json" in extra
    assert len(extra["telegram_update_json"]) <= 10_000
