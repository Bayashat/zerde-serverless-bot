from datetime import datetime, timezone
from typing import Any

# Evening: 11–21 UTC. Morning: 22–06 UTC
EVENING_HOURS = range(11, 22)

MORNING_HOUR_THRESHOLD = 7  # hour < 7 → morning slot for intro

_INTRO_TEXTS: dict[tuple[str, str], str] = {
    ("zh", "morning"): "🌞早上好\n\n这里是现在的重要IT新闻：",
    ("zh", "evening"): "🌙 晚上好\n\n这里是现在的重要IT新闻：",
    ("kk", "morning"): "🌞 Қайырлы таң!\n\n Қазіргі басты IT жаңалықтар:",
    ("kk", "evening"): "🌙 Қайырлы кеш!\n\n Қазіргі басты IT жаңалықтар:",
}
DEFAULT_INTRO_LANG = "kk"


def get_greeting_and_max_age_hours() -> tuple[float, str]:
    """Return (max_age_hours, greeting) for current UTC hour. Never returns None."""
    hour = datetime.now(timezone.utc).hour
    if hour in EVENING_HOURS:
        return 10.5, hour  # 09:00–19:00 Almaty: 10.5h buffer
    return 14.5, hour  # 19:00–09:00 Almaty: 14.5h buffer


def get_intro_text(chat_lang: str, current_hour: int) -> str:
    """Return intro text based on chat language and time-of-day slot."""
    slot = "morning" if current_hour < MORNING_HOUR_THRESHOLD else "evening"
    return _INTRO_TEXTS.get((chat_lang, slot), _INTRO_TEXTS[(DEFAULT_INTRO_LANG, slot)])


def extract_event(event: dict[str, Any]) -> dict[str, Any]:
    """Extract chat_id and chat_lang from event."""
    chat_id = event.get("chat_id")
    chat_lang = event.get("chat_lang")
    if not chat_id or not chat_lang:
        raise ValueError("chat_id and chat_lang are required")
    return chat_id, chat_lang
