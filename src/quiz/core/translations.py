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
        "difficulty_easy_medium": "Easy-Medium 🟡",
        "difficulty_medium": "Medium 🟡",
        "difficulty_medium_hard": "Medium-Hard 🟠",
        "difficulty_hard": "Hard 🔴",
        "difficulty_expert": "Expert ⚫",
        "leaderboard_header": "🏆 <b>Weekly Leaderboard</b>\n<i>(This week's points — resets each week)</i>\n\n",
        "leaderboard_empty": "Nobody has answered yet.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "genquiz_queued": (
            "⏳ Your quiz request is saved. The bot will retry it in the background. You do not need to "
            "send it again."
        ),
        "genquiz_processing": "⏳ Your quiz request is being processed. Please do not send it again.",
        "genquiz_needs_review": (
            "⚠️ An administrator needs to check the quiz delivery or records. Please do not send the " "request again."
        ),
        "genquiz_expired": "⌛ This quiz request expired before publication. You can send a new /genquiz command.",
        "genquiz_rejected": "❌ This command could not be accepted. Please send a new valid /genquiz command.",
        "genquiz_unconfirmed": (
            "⚠️ The quiz request status could not be confirmed. Please ask an administrator to check it "
            "and do not resend it."
        ),
        "season_champion_header": "🎖️ <b>Season Champion! (4 weeks)</b>\n\n",
        "season_champion_empty": "No weekly winners this season.",
        "season_wins_label": "{wins} wins",
        "quiz_source_label": "📚 Source: {source}",
    },
    "kk": {
        "quiz_announcement": (
            "🎯 <b>Күнделікті IT сұрағы</b>\n\n"
            "📊 Деңгейі: <b>{difficulty_label}</b>\n"
            "💰 Дұрыс жауап үшін: <b>{points} ұпай</b>"
        ),
        "difficulty_easy": "Оңай 🟢",
        "difficulty_easy_medium": "Оңайлау 🟡",
        "difficulty_medium": "Орташа 🟡",
        "difficulty_medium_hard": "Қиындау 🟠",
        "difficulty_hard": "Қиын 🔴",
        "difficulty_expert": "Эксперт ⚫",
        "leaderboard_header": "🏆 <b>Апталық рейтинг</b>\n<i>(Осы аптадағы ұпайлар — әр аптада нөлденеді)</i>\n\n",
        "leaderboard_empty": "Әзірге ешкім жауап берген жоқ.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "genquiz_queued": (
            "⏳ Quiz сұрауы сақталды. Бот оны фондық режимде қайта орындап көреді. Қайта жіберудің " "қажеті жоқ."
        ),
        "genquiz_processing": "⏳ Quiz сұрауы өңделіп жатыр. Оны қайта жібермеңіз.",
        "genquiz_needs_review": "⚠️ Әкімші Quiz жіберілуін немесе жазбаларын тексеруі керек. Сұрауды қайта жібермеңіз.",
        "genquiz_expired": (
            "⌛ Бұл Quiz сұрауының мерзімі жарияланбай тұрып аяқталды. Жаңа /genquiz пәрменін жіберуге " "болады."
        ),
        "genquiz_rejected": "❌ Бұл пәрмен қабылданбады. Жаңа дұрыс /genquiz пәрменін жіберіңіз.",
        "genquiz_unconfirmed": (
            "⚠️ Quiz сұрауының күйін растау мүмкін болмады. Әкімшіден тексеруді сұраңыз, сұрауды қайта " "жібермеңіз."
        ),
        "season_champion_header": "🎖️ <b>Маусым чемпионы! (4 апта)</b>\n\n",
        "season_champion_empty": "Бұл маусымда апта жеңімпаздары болмады.",
        "season_wins_label": "{wins} жеңіс",
        "quiz_source_label": "📚 Дереккөз: {source}",
    },
    "ru": {
        "quiz_announcement": (
            "🎯 <b>Ежедневный IT вопрос</b>\n\n"
            "📊 Сложность: <b>{difficulty_label}</b>\n"
            "💰 За правильный ответ: <b>{points} очков</b>"
        ),
        "difficulty_easy": "Лёгкий 🟢",
        "difficulty_easy_medium": "Несложный 🟡",
        "difficulty_medium": "Средний 🟡",
        "difficulty_medium_hard": "Умеренно сложный 🟠",
        "difficulty_hard": "Сложный 🔴",
        "difficulty_expert": "Эксперт ⚫",
        "leaderboard_header": (
            "🏆 <b>Еженедельный рейтинг</b>\n<i>(Очки за эту неделю — сбрасываются еженедельно)</i>\n\n"
        ),
        "leaderboard_empty": "Пока никто не отвечал.",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "genquiz_queued": (
            "⏳ Запрос на Quiz сохранён. Бот повторит попытку в фоновом режиме. Отправлять запрос заново " "не нужно."
        ),
        "genquiz_processing": "⏳ Запрос на Quiz обрабатывается. Не отправляйте его повторно.",
        "genquiz_needs_review": (
            "⚠️ Администратору нужно проверить отправку или записи Quiz. Не отправляйте запрос " "повторно."
        ),
        "genquiz_expired": "⌛ Срок этого запроса на Quiz истёк до публикации. Можно отправить новую команду /genquiz.",
        "genquiz_rejected": "❌ Эта команда не была принята. Отправьте новую корректную команду /genquiz.",
        "genquiz_unconfirmed": (
            "⚠️ Не удалось подтвердить состояние запроса на Quiz. Попросите администратора проверить "
            "его и не отправляйте запрос повторно."
        ),
        "season_champion_header": "🎖️ <b>Чемпион сезона! (4 недели)</b>\n\n",
        "season_champion_empty": "В этом сезоне не было победителей недели.",
        "season_wins_label": "{wins} побед",
        "quiz_source_label": "📚 Источник: {source}",
    },
    "zh": {
        "quiz_announcement": (
            "🎯 <b>每日 IT 问答</b>\n\n" "📊 难度：<b>{difficulty_label}</b>\n" "💰 答对得：<b>{points} 分</b>"
        ),
        "difficulty_easy": "简单 🟢",
        "difficulty_easy_medium": "中低难度 🟡",
        "difficulty_medium": "中等 🟡",
        "difficulty_medium_hard": "中高难度 🟠",
        "difficulty_hard": "困难 🔴",
        "difficulty_expert": "专家 ⚫",
        "leaderboard_header": "🏆 <b>每周排行榜</b>\n<i>（本周积分，每周重置）</i>\n\n",
        "leaderboard_empty": "还没有人答题。",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD：{remaining}/{total}",
        "genquiz_queued": "⏳ Quiz 请求已保留，机器人会在后台继续尝试，无需重新发送。",
        "genquiz_processing": "⏳ Quiz 请求正在处理中，请勿重复提交。",
        "genquiz_needs_review": "⚠️ Quiz 的发送或记录状态需要管理员核对，请勿重复提交。",
        "genquiz_expired": "⌛ 此 Quiz 请求已在发布前过期，可以重新发送 /genquiz 命令。",
        "genquiz_rejected": "❌ 此命令未被接受，请重新发送有效的 /genquiz 命令。",
        "genquiz_unconfirmed": "⚠️ 无法确认 Quiz 请求状态，请联系管理员核对，勿重复提交。",
        "season_champion_header": "🎖️ <b>本赛季冠军！（4周）</b>\n\n",
        "season_champion_empty": "本赛季暂无周冠军。",
        "season_wins_label": "{wins} 次冠军",
        "quiz_source_label": "📚 来源：{source}",
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
