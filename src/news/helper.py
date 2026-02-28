from datetime import datetime, timezone

# UTC hour ranges map to digest slots (Almaty UTC+5: 09:00, 13:00, 19:00 = 04:00, 08:00, 14:00 UTC)
TIME_OF_DAY_BY_HOUR = (
    (range(3, 7), "Таңғы"),  # 03–06 UTC: Morning
    (range(7, 11), "Түскі"),  # 07–10 UTC: Noon
    (range(11, 17), "Кешкі"),  # 11–16 UTC: Evening
)
GREETINGS = {
    "Таңғы": "🌞 Таңғы жаңалықтар",
    "Түскі": "🌆 Түскі жаңалықтар",
    "Кешкі": "🌙 Кешкі жаңалықтар",
}


def get_greeting() -> str:
    """Return time-of-day greeting string (Kazakh) based on current UTC hour."""
    hour = datetime.now(timezone.utc).hour
    for hour_range, label in TIME_OF_DAY_BY_HOUR:
        if hour in hour_range:
            return GREETINGS[label]
    return GREETINGS["Кешкі"] if hour < 3 else GREETINGS["Таңғы"]
