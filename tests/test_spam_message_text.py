"""Tests for collect_spam_screen_text (quote + external_reply aggregation)."""

from services.spam.message_text import collect_spam_screen_text
from services.spam.rule_filter import RuleBasedSpamFilter

_USER_ID = 123456
_CHAT_ID = -1001244628965

_QUOTE_SPAM_SAMPLE = {
    "message_id": 173624,
    "from": {"id": 8745479751, "is_bot": False, "first_name": "Лера", "is_premium": True},
    "chat": {
        "id": -1001244628965,
        "title": "Aman world әңгіме",
        "username": "amanchikworld",
        "type": "supergroup",
    },
    "text": "Очень быстрый!!! спасибо!",
    "external_reply": {
        "origin": {
            "type": "channel",
            "chat": {
                "id": -1003550346304,
                "title": "Nord VPN - Бесплатный ВПН",
                "username": "NordVPNq",
                "type": "channel",
            },
            "message_id": 10,
            "date": 1775753663,
        },
        "chat": {
            "id": -1003550346304,
            "title": "Nord VPN - Бесплатный ВПН",
            "username": "NordVPNq",
            "type": "channel",
        },
        "message_id": 10,
    },
    "quote": {
        "text": (
            "🛡NordVPN — лучший бесплатный ВПН \n"
            "Быстрый. Бесплатный. Неубиваемый.\n\n"
            "🛰 Работает в РФ как часы: обходит блокировки РКН, ТСПУ и белые списки."
        ),
        "position": 0,
        "is_manual": True,
    },
}


def test_collect_includes_quote_and_external_reply_context() -> None:
    out = collect_spam_screen_text(_QUOTE_SPAM_SAMPLE)
    assert "Очень быстрый" in out
    assert "NordVPN" in out or "ВПН" in out
    assert "Nord VPN" in out
    assert "@NordVPNq" in out


def test_collect_quote_only_non_empty() -> None:
    msg = {
        "quote": {"text": "VPN реклама впн", "position": 0},
    }
    assert collect_spam_screen_text(msg).strip() == "VPN реклама впн"


def test_combined_text_triggers_vpn_rule_on_harmless_surface_text() -> None:
    """Layer-1 must see quoted VPN copy, not only the user's short reply."""
    f = RuleBasedSpamFilter()
    combined = collect_spam_screen_text(_QUOTE_SPAM_SAMPLE)
    score, rules = f.check(combined, _USER_ID, _CHAT_ID)
    assert score > 0.3
    assert "vpn_pattern" in rules


def test_empty_message_returns_empty_string() -> None:
    assert collect_spam_screen_text({}) == ""
