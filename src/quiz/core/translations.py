"""Localised UI strings for the Quiz Lambda."""

from typing import Any

from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

DEFAULT_LANG = "kk"

TRANSLATIONS = {
    "en": {
        "quiz_announcement": (
            "🎯 <b>Daily IT question</b>\n\n"
            "📊 Difficulty: <b>{difficulty_label}</b>\n"
            "💰 For correct answer: <b>{points} points</b>"
        ),
        "difficulty_easy": "Easy 🟢",
        "difficulty_medium": "Medium 🟡",
        "difficulty_hard": "Hard 🔴",
        "difficulty_expert": "Expert ⚫",
        "leaderboard_header": "🏆 <b>Weekly Leaderboard</b>\n<i>(Points are accumulated)</i>\n\n",
        "leaderboard_empty": "Nobody has answered yet.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
    },
    "kk": {
        "quiz_announcement": (
            "🎯 <b>Күнделікті IT сұрағы</b>\n\n"
            "📊 Деңгейі: <b>{difficulty_label}</b>\n"
            "💰 Дұрыс жауап үшін: <b>{points} ұпай</b>"
        ),
        "difficulty_easy": "Оңай 🟢",
        "difficulty_medium": "Орташа 🟡",
        "difficulty_hard": "Қиын 🔴",
        "difficulty_expert": "Эксперт ⚫",
        "leaderboard_header": "🏆 <b>Апталық рейтинг</b>\n<i>(Ұпайлар жинақталады)</i>\n\n",
        "leaderboard_empty": "Әзірге ешкім жауап берген жоқ.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
    },
    "ru": {
        "quiz_announcement": (
            "🎯 <b>Ежедневный IT вопрос</b>\n\n"
            "📊 Сложность: <b>{difficulty_label}</b>\n"
            "💰 За правильный ответ: <b>{points} очков</b>"
        ),
        "difficulty_easy": "Лёгкий 🟢",
        "difficulty_medium": "Средний 🟡",
        "difficulty_hard": "Сложный 🔴",
        "difficulty_expert": "Эксперт ⚫",
        "leaderboard_header": "🏆 <b>Еженедельный рейтинг</b>\n<i>(Очки накапливаются)</i>\n\n",
        "leaderboard_empty": "Пока никто не отвечал.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
    },
    "zh": {
        "quiz_announcement": (
            "🎯 <b>每日 IT 问答</b>\n\n" "📊 难度：<b>{difficulty_label}</b>\n" "💰 答对得：<b>{points} 分</b>"
        ),
        "difficulty_easy": "简单 🟢",
        "difficulty_medium": "中等 🟡",
        "difficulty_hard": "困难 🔴",
        "difficulty_expert": "专家 ⚫",
        "leaderboard_header": "🏆 <b>每周排行榜</b>\n<i>（积分累计计算）</i>\n\n",
        "leaderboard_empty": "还没有人答题。",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD：{remaining}/{total}",
    },
}


def get_translated_text(key: str, lang_code: str = "kk", **kwargs: Any) -> str:
    """Get translated text for *key*, falling back to DEFAULT_LANG."""
    target_lang = lang_code if lang_code in TRANSLATIONS else DEFAULT_LANG
    text = TRANSLATIONS[target_lang].get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))

    try:
        if kwargs:
            text = text.format(**kwargs)
    except KeyError as e:
        logger.warning("Missing format key in translation", extra={"error": str(e), "key": key})

    return text
