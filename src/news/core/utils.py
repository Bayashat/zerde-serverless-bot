"""Shared utilities: time windows, intro texts, and event parsing."""

from datetime import datetime, timezone
from typing import Any

# Evening: 11–21 UTC. Morning: 22–06 UTC
EVENING_HOURS = range(11, 22)
MORNING_HOUR_THRESHOLD = 7  # hour < 7 → morning slot

_INTRO_TEXTS: dict[tuple[str, str], str] = {
    ("zh", "morning"): "🌞早上好\n\n这里是现在的重要IT新闻：",
    ("zh", "evening"): "🌙 晚上好\n\n这里是现在的重要IT新闻：",
    ("kk", "morning"): "🌞 Қайырлы таң!\n\nҚазіргі басты IT жаңалықтар:",
    ("kk", "evening"): "🌙 Қайырлы кеш!\n\nҚазіргі басты IT жаңалықтар:",
    ("ru", "morning"): "🌞 Доброе утро\n\nГлавные IT-новости за прошедшие сутки:",
    ("ru", "evening"): "🌙 Добрый вечер\n\nГлавные IT-новости за прошедшие сутки:",
}
DEFAULT_INTRO_LANG = "kk"


def get_greeting_and_max_age_hours(chat_lang: str) -> tuple[float, int]:
    """Return (max_age_hours, current_utc_hour) for the active time window."""
    hour = datetime.now(timezone.utc).hour
    if chat_lang == "ru":
        return 24, hour
    if hour in EVENING_HOURS:
        return 10.5, hour  # 09:00–19:00 Almaty: 10.5h buffer
    return 14.5, hour  # 19:00–09:00 Almaty: 14.5h buffer


def get_intro_text(chat_lang: str, current_hour: int) -> str:
    """Return localised intro string for the current time-of-day slot."""
    slot = "morning" if current_hour < MORNING_HOUR_THRESHOLD else "evening"
    return _INTRO_TEXTS.get((chat_lang, slot), _INTRO_TEXTS[(DEFAULT_INTRO_LANG, slot)])


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
