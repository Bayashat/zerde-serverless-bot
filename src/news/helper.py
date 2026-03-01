from datetime import datetime, timezone

# Evening: 11–21 UTC. Morning: 22–06 UTC
EVENING_HOURS = range(11, 22)
MORNING_GREETING = "🌞 Қайырлы таң!"
EVENING_GREETING = "🌙 Қайырлы кеш!"


def get_greeting_and_max_age_hours() -> tuple[float, str]:
    """Return (max_age_hours, greeting) for current UTC hour. Never returns None."""
    hour = datetime.now(timezone.utc).hour
    if hour in EVENING_HOURS:
        return 10.5, EVENING_GREETING  # 09:00–19:00 Almaty: 10.5h buffer
    return 14.5, MORNING_GREETING  # 19:00–09:00 Almaty: 14.5h buffer


def get_chat_lang_by_id(chat_id: str) -> str:
    """Return chat language based on chat ID."""
    if chat_id == "-1002211083217":
        return "zh"
    return "kk"


def get_intro_text(chat_lang: str) -> str:
    """Return intro text based on chat language."""
    if chat_lang == "zh":
        return "这里是现在的重要IT新闻："
    return "Міне, қазіргі басты IT жаңалықтар:"
