"""
Service for formatting Telegram messages.
"""

from typing import Any

from aws_lambda_powertools import Logger
from services import BOT_DESCRIPTION, BOT_INSTRUCTIONS, BOT_NAME, DEFAULT_LANG

logger = Logger()


TRANSLATIONS = {
    "en": {
        "start_message": (
            "👋 Welcome to {BOT_NAME}!\n\n"
            "I can help you with {BOT_DESCRIPTION}\n"
            "Use the /help command to view available commands."
        ),
        "help_message": (
            "🤖 <b>Zerde Bot Instructions</b>:\n\n"
            "This bot works automatically.\n\n"
            "🔹 <b>For new members:</b>\n"
            "You need to click the 'I am human' button when joining the group, "
            "otherwise you will not be able to send messages.\n\n"
            "🔹 <b>For administrators:</b>\n"
            "/stats - View statistics of the group\n\n"
            "/support - Ask for technical support"
        ),
        "echo_message": "❌ Unknown command. Use /help to view available commands.",
        "error_occurred": "❌ An error occurred. Please try again later.",
        "unknown_action": "❌ Unknown action.",
        "invalid_data": "❌ Invalid data.",
        "welcome_verification": (
            "👋 Welcome {MENTION}!\n\n"
            "To ensure quality, please verify you are human.\n\n"
            "⏳ <b>Time limit: 60 seconds</b>\n\n"
            "(Auto-kick if timed out)"
        ),
        "welcome_verified": ("Hello {MENTION}! Welcome to Kazakh IT community!"),
        "verification_successful": "✅ Verified!",
        "stats_admin_only": "Only administrators can view /stats.",
        "stats_error": "Failed to load stats.",
        "only_user_may_verify": "Only the user who joined may verify.",
        "activity_low": "🌱 Low",
        "activity_medium": "🌿 Medium",
        "activity_high": "🔥 High",
        "stats_message": (
            "📊 <b>Chat statistics</b>\n"
            "⏰ Since {start_date}\n\n"
            "👥 <b>Joined members:</b> {total} users\n"
            "✅ <b>Passed captchas:</b> {verified} items\n\n"
            "📈 <b>Overall activity:</b> {activity_level}"
        ),
        "support_message": "👨‍💻 Technical support\nFor questions: @bayashat",
    },
    "kk": {
        "start_message": (
            "👋 {BOT_NAME} ботқа қош келдіңіз!\n\n"
            "Мен сізге {BOT_DESCRIPTION} бойынша көмектесе аламын.\n"
            "/help командасын қолданып, қолжетімді командаларды көруге болады."
        ),
        "help_message": (
            "🤖 <b>Zerde Bot Нұсқаулығы</b>:\n\n"
            "Бұл бот автоматты түрде жұмыс істейді.\n\n"
            "🔹 <b>Жаңа мүшелер үшін:</b>\n"
            "Топқа қосылған кезде 'Мен адаммын' түймесін басу қажет, әйтпесе хабарлама жаза алмайды.\n\n"
            "🔹 <b>Админдер үшін:</b>\n"
            "/stats - Топтағы статикалық ақпаратты көру\n\n"
            "/support - Техникалық қолдау сұрау"
        ),
        "echo_message": "❌ Белгісіз команда. Қолжетімді командаларды көру үшін /help командасын қолданыңыз.",
        "error_occurred": "❌ Қате орын алды. Кейінірек қайталап көріңіз.",
        "unknown_action": "❌ Белгісіз әрекет.",
        "invalid_data": "❌ Белгісіз мәлімет.",
        "welcome_verification": (
            "👋 Welcome {MENTION}!\n\n"
            "Топ сапасын сақтау үшін, бот емес екеніңізді растаңыз.\n\n"
            "⏳ <b>Уақыт шектеулі: 60 секунд</b>\n\n"
            "(Уақыт өтсе, автоматты түрде шығарыласыз)"
        ),
        "welcome_verified": (
            "{MENTION} 👋\n\nҚазақша IT қауымдастыққа қош келдіңіз! Жаңа идеялар мен жетістіктерге бірге жетейік. 🌟"
        ),
        "verification_successful": "✅ Расталды",
        "stats_admin_only": "Тек әкімшілер үшін қолжетімді.",
        "stats_error": "Статистиканы жүктеу кезінде қате орын алды.",
        "only_user_may_verify": "Тек жаңадан қосылған қолданушы үшін қолжетімді.",
        "activity_low": "🌱 Төмен",
        "activity_medium": "🌿 Орташа",
        "activity_high": "🔥 Жоғары",
        "stats_message": (
            "📊 <b>Топ статистикасы</b>\n"
            "⏰ {start_date} бастап\n\n"
            "👥 <b>Қосылған мүшелер:</b> {total} қолданушы\n"
            "✅ <b>Өткен капчалар:</b> {verified} дана\n\n"
            "📈 <b>Жалпы белсенділік:</b> {activity_level}"
        ),
        "support_message": "👨‍💻 Техникалық қолдау\nСұрақтар бойынша: @bayashat",
    },
}


def get_translated_text(key: str, lang_code: str = "kk", **kwargs: Any) -> str:
    """
    Get text translation for a given key and language code.
    Falls back to English if language not supported.
    """
    target_lang = lang_code if lang_code in TRANSLATIONS else DEFAULT_LANG

    text = TRANSLATIONS[target_lang].get(key, key)

    try:
        text = text.format(
            BOT_NAME=BOT_NAME,
            BOT_DESCRIPTION=BOT_DESCRIPTION,
            BOT_INSTRUCTIONS=BOT_INSTRUCTIONS,
            **kwargs,
        )
    except KeyError as e:
        logger.warning(f"Missing format key in translation: {e}")

    return text
