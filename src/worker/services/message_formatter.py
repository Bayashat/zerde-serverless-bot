"""
Service for formatting Telegram messages.
"""

from typing import Any

from aws_lambda_powertools import Logger
from services import DEFAULT_LANG

logger = Logger()

TRANSLATIONS = {
    "en": {
        "start_message": (
            "👋 <b>Hello! I am Zerde — a smart assistant for IT communities.</b> 🤖\n\n"
            "My main task is to protect chats from spam bots and gather useful statistics.\n\n"
            "🚀 <b>How to get started?</b>\n"
            "1. Add me to your group.\n"
            "2. Promote me to <b>Admin</b>.\n\n"
            "<i>For full information, click /help.</i>\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "help_message": (
            "🤖 <b>Zerde Bot: Usage Guide</b>\n\n"
            "This bot operates automatically within groups.\n\n"
            "🛡️ <b>For New Members (Anti-Spam):</b>\n"
            "Upon joining, you must click the <b>'I am human'</b> button.\n"
            "⚠️ <i>Warning: If the button is not clicked within 60 seconds, you will be automatically removed.</i>\n\n"
            "📊 <b>For Admins:</b>\n"
            "• /stats — View group statistics and activity levels.\n"
            "• /start — Restart the bot (if unresponsive).\n\n"
            "⚙️ <b>Setup:</b>\n"
            "For proper functionality, the bot must be granted <i>'Delete Messages'</i> "
            "and <i>'Ban Users'</i> permissions.\n\n"
            "👨‍💻 <b>Support:</b>\n"
            "/support — Report a bug or suggest a feature."
        ),
        "stats_message": (
            "📊 <b>Chat statistics</b>\n"
            "⏰ Since {start_date}\n\n"
            "👥 <b>Total Joins:</b> {total} users\n"
            "✅ <b>Verified captchas:</b> {verified} items\n\n"
            "📈 <b>Overall activity:</b> {activity_level}"
        ),
        "private_message": (
            "👋 <b>Hello! I am Zerde — a smart assistant for IT communities.</b> 🤖\n\n"
            "My main task is to protect chats from spam bots and gather useful statistics.\n\n"
            "⚠️ <b>This bot only works in chats/groups. "
            "If you want to add me to your private chat, contact <i>@bayashat</i>!</b>\n\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "support_message": "👨‍💻 Technical support\nFor questions: <i>@bayashat</i>",
        "welcome_verification": (
            "👋 Welcome {MENTION}!\n\n"
            "To ensure quality, please verify you are human.\n\n"
            "⏳ <b>Time limit: 60 seconds</b>\n\n"
            "(Auto-kick if timed out)"
        ),
        "welcome_verified": ("Hello {MENTION}! Welcome to Kazakh IT community!"),
        "verification_successful": "✅ Verified!",
        "activity_low": "🌱 Low",
        "activity_medium": "🌿 Medium",
        "activity_high": "🔥 High",
        "error_occurred": "❌ An error occurred. Please try again later.",
        "unknown_action": "❌ Unknown action.",
        "invalid_data": "❌ Invalid data.",
        "stats_admin_only": "❌ Only administrators can view /stats.",
        "stats_error": "❌ Failed to load stats.",
        "only_user_may_verify": "❌ Only the user who joined may verify.",
        "vote_ban_initiated": (
            "🗳️ <b>Vote to Ban</b>\n\n"
            "👤 <b>Initiator:</b> {INITIATOR}\n"
            "🎯 <b>Target:</b> {TARGET}\n\n"
            "📊 <b>Current votes:</b>\n"
            "🚫 Ban: {BAN_COUNT}\n"
            "💚 Forgive: {FORGIVE_COUNT}\n\n"
            "⚠️ <b>Threshold:</b> {THRESHOLD} votes needed to ban\n\n"
            "Vote below 👇"
        ),
        "vote_ban_updated": (
            "📊 <b>Vote Status Updated</b>\n\n"
            "🚫 Ban: {BAN_COUNT}\n"
            "💚 Forgive: {FORGIVE_COUNT}\n\n"
            "⚠️ <b>Threshold:</b> {THRESHOLD} votes needed"
        ),
        "vote_ban_success": "✅ User has been banned! The ban threshold was reached.",
        "vote_recorded": "✅ Your vote has been recorded!",
        "vote_ban_reply_required": "❌ Please reply to a user's message to initiate vote-to-ban.",
        "vote_ban_cannot_ban_admin": "❌ Cannot initiate ban vote against administrators.",
        "vote_ban_cannot_ban_self": "❌ You cannot initiate a ban vote against yourself.",
        "vote_ban_session_not_found": "❌ Vote session not found or expired.",
    },
    "kk": {
        "start_message": (
            "👋 <b>Сәлем! Мен Zerde — IT қауымдастықтардың ақылды көмекшісімін.</b> 🤖\n\n"
            "Менің негізгі міндетім — чатты спам-боттардан қорғау және пайдалы статистика жинау.\n\n"
            "🚀 <b>Мені қалай іске қосуға болады?</b>\n"
            "1. Мені өз тобыңызға қосыңыз (Add to Group).\n"
            "2. Маған <b>Админ (Admin)</b> құқығын беріңіз.\n\n"
            "<i>Толық ақпарат алу үшін /help командасын басыңыз.</i>\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "help_message": (
            "🤖 <b>Zerde Bot: Пайдалану нұсқаулығы</b>\n\n"
            "Бұл бот топтарда автоматты түрде жұмыс істейді.\n\n"
            "🛡️ <b>Жаңа мүшелер үшін (Anti-Spam):</b>\n"
            "Топқа қосылған кезде арнайы <b>«Мен адаммын»</b> түймесін басу қажет.\n"
            "⚠️ <i>Ескерту: Түйме 60 секунд ішінде басылмаса, сіз топтан автоматты түрде шығарыласыз.</i>\n\n"
            "📊 <b>Админдер үшін:</b>\n"
            "• /stats — Топтың статистикасын және белсенділігін көру.\n"
            "• /start — Ботты қайта іске қосу (егер қатып қалса).\n\n"
            "⚙️ <b>Орнату:</b>\n"
            "Бот дұрыс жұмыс істеуі үшін, оған <i>«Delete Messages»</i> "
            "және <i>«Ban Users»</i> құқықтары берілуі керек.\n\n"
            "👨‍💻 <b>Қолдау қызметі:</b>\n"
            "/support — Қате туралы хабарлау немесе ұсыныс айту."
        ),
        "stats_message": (
            "📊 <b>Топ статистикасы</b>\n"
            "⏰ {start_date} бастап\n\n"
            "👥 <b>Жалпы қосылған мүшелер:</b> {total} қолданушы\n"
            "✅ <b>Расталған капчалар:</b> {verified} дана\n\n"
            "📈 <b>Жалпы белсенділік:</b> {activity_level}"
        ),
        "private_message": (
            "🤖 <b>Сәлем! Мен Zerde — IT қауымдастықтардың ақылды көмекшісімін.</b>\n\n"
            "Менің негізгі міндетім — чатты спам-боттардан қорғау және пайдалы статистика жинау.\n\n"
            "⚠️ <b>Бұл бот тек чаттарда/топтарда қызмет көрсетеді, "
            "егер өз тобыңызға қосқыңыз келсе <i>@bayashat</i> хабарласыңыз!</b>\n\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "support_message": "👨‍💻 Техникалық қолдау\nСұрақтар бойынша: <i>@bayashat</i>",
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
        "activity_low": "🌱 Төмен",
        "activity_medium": "🌿 Орташа",
        "activity_high": "🔥 Жоғары",
        "error_occurred": "❌ Қате орын алды. Кейінірек қайталап көріңіз.",
        "unknown_action": "❌ Белгісіз әрекет.",
        "invalid_data": "❌ Белгісіз мәлімет.",
        "stats_admin_only": "❌ Тек әкімшілер үшін қолжетімді.",
        "stats_error": "❌ Статистиканы жүктеу кезінде қате орын алды.",
        "only_user_may_verify": "❌ Тек жаңадан қосылған қолданушы үшін қолжетімді.",
        "vote_ban_initiated": (
            "🗳️ <b>Дауыс беру арқылы бан</b>\n\n"
            "👤 <b>Бастаушы:</b> {INITIATOR}\n"
            "🎯 <b>Мақсат:</b> {TARGET}\n\n"
            "📊 <b>Ағымдағы дауыстар:</b>\n"
            "🚫 Бан: {BAN_COUNT}\n"
            "💚 Кешіру: {FORGIVE_COUNT}\n\n"
            "⚠️ <b>Шегі:</b> Банға {THRESHOLD} дауыс қажет\n\n"
            "Төменде дауыс беріңіз 👇"
        ),
        "vote_ban_updated": (
            "📊 <b>Дауыс берілу жағдайы жаңартылды</b>\n\n"
            "🚫 Бан: {BAN_COUNT}\n"
            "💚 Кешіру: {FORGIVE_COUNT}\n\n"
            "⚠️ <b>Шегі:</b> {THRESHOLD} дауыс қажет"
        ),
        "vote_ban_success": "✅ Қолданушы бандалды! Бан шегіне жетілді.",
        "vote_recorded": "✅ Сіздің дауысыңыз тіркелді!",
        "vote_ban_reply_required": "❌ Дауыс беру арқылы банды бастау үшін қолданушының хабарламасына жауап беріңіз.",
        "vote_ban_cannot_ban_admin": "❌ Әкімшілерге қарсы дауыс беруге болмайды.",
        "vote_ban_cannot_ban_self": "❌ Өзіңізге қарсы дауыс бере алмайсыз.",
        "vote_ban_session_not_found": "❌ Дауыс беру сессиясы табылмады немесе мерзімі өтті.",
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
            **kwargs,
        )
    except KeyError as e:
        logger.warning(f"Missing format key in translation: {e}")

    return text
