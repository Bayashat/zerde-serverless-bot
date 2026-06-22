"""Tests for spam screening text and AI context rendering."""

from services.spam.message_text import build_spam_context_payload, collect_spam_screen_text, format_spam_ai_context
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


def test_build_context_payload_includes_reply_quote_and_rules() -> None:
    msg = {
        "message_id": 184178,
        "text": "Смекта 2000тг деп куткарам.",
        "reply_to_message": {
            "message_id": 184163,
            "from": {"id": 845486913, "username": "yeskabyl", "first_name": "Ruslanuly"},
            "text": "заблокировал(а) Grand Theft Auto VI [IHN] (@fafnirdragon)",
        },
        "quote": {"text": "Смекта 2000 3000тг ушын ба?"},
    }

    payload = build_spam_context_payload(msg, rule_score=0.3, triggered_rules=["money_pattern"])

    assert payload["current_message"] == "Смекта 2000тг деп куткарам."
    assert payload["reply_to_message"]["from"] == "@yeskabyl"
    assert "заблокировал" in payload["reply_to_message"]["text"]
    assert payload["quote"] == "Смекта 2000 3000тг ушын ба?"
    assert payload["rule_score"] == 0.3
    assert payload["triggered_rules"] == ["money_pattern"]


def test_format_spam_ai_context_renders_current_and_recent_context() -> None:
    rendered = format_spam_ai_context(
        text="combined fallback",
        message_context={
            "current_message": "Смекта 2000тг деп куткарам.",
            "reply_to_message": {"from": "@yeskabyl", "text": "заблокировал(а) Grand Theft Auto VI"},
            "rule_score": 0.3,
            "triggered_rules": ["money_pattern"],
        },
        recent_context=[
            {"display_name": "Aman", "text": "ФГДС и колоноскапия жасап кету керек."},
            {"display_name": "Lio", "text": "За что."},
        ],
    )

    assert "CURRENT_MESSAGE:" in rendered
    assert "Смекта 2000тг деп куткарам." in rendered
    assert "REPLY_TO_MESSAGE:" in rendered
    assert "triggered_rules=['money_pattern']" in rendered
    assert "RECENT_GROUP_MESSAGES" in rendered
    assert "Aman: ФГДС и колоноскапия жасап кету керек." in rendered
