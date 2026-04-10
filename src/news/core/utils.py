"""Shared utilities: time windows, intro texts, and event parsing."""

from typing import Any

_INTRO_TEXTS: dict[str, str] = {
    "zh": "🌞早上好\n\n这里是现在的重要IT新闻：",
    "kk": "🌞 Қайырлы таң!\n\nҚазіргі басты IT жаңалықтар:",
    "ru": "🌞 Доброе утро\n\nГлавные IT-новости за прошедшие сутки:",
}
DEFAULT_INTRO_LANG = "kk"


def get_intro_text(chat_lang: str) -> str:
    """Return localised intro string for the current time-of-day slot."""
    return _INTRO_TEXTS.get(chat_lang, _INTRO_TEXTS[DEFAULT_INTRO_LANG])


def extract_event(event: dict[str, Any]) -> tuple[list[str], str]:
    """Extract and validate chat_ids and lang from the EventBridge event."""
    chat_ids = event.get("chat_ids")
    lang = event.get("lang")
    if not chat_ids or not lang:
        raise ValueError("chat_ids and lang are required in event payload")
    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]
    elif isinstance(chat_ids, int):
        chat_ids = [str(chat_ids)]
    return chat_ids, lang
