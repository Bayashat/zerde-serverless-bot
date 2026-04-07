"""Localised UI strings for the Telegram bot."""

from typing import Any

from core.config import DEFAULT_LANG
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

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
            "✅ <b>Verified captchas:</b> {verified} items\n"
            "🔫 <b>Banned by vote:</b> {banned} users\n\n"
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
        "welcome_verified": "Hello {MENTION}! Welcome to Kazakh IT community!",
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
        "voteban_usage": "❌ Usage: Reply to a message with /voteban to start voting to ban that user.",
        "voteban_self": "❌ You cannot vote to ban yourself.",
        "voteban_admin": "❌ You cannot vote to ban administrators.",
        "not_in_group": "❌ You are not in the group. This bot does not work outside of groups.",
        "voteban_initiated": ("🗳️ <b>Vote to Ban</b>\n\n" "👤 Initiated by: {INITIATOR}\n" "🎯 Target: {TARGET}"),
        "voteban_vote_recorded": "✅ Your vote has been recorded.",
        "voteban_already_voted": "⚠️ You have already voted on this ban.",
        "voteban_banned": (
            "⚖️ <b>User Banned by Vote</b>\n\n"
            "🎯 {TARGET} has been banned after receiving {VOTES_FOR} votes.\n\n"
            "🔫 Voted to ban: {VOTERS_FOR}"
        ),
        "voteban_forgiven": (
            "💚 <b>Vote to Ban Cancelled</b>\n\n"
            "🎯 {TARGET} has been forgiven with {VOTES_AGAINST} forgive votes.\n\n"
            "👼 Voted to forgive: {VOTERS_AGAINST}"
        ),
        "quizstats_response": (
            "🧠 <b>Your Quiz Stats</b>\n\n"
            "🏆 Score: <b>{score}</b> points\n"
            "🔥 Streak: <b>{streak}</b> days\n"
            "⭐ Best streak: <b>{best_streak}</b> days\n"
            "📊 Rank: <b>#{rank}</b> / {total_players} players"
        ),
        "quizstats_no_data": "🧠 You haven't answered any quizzes yet. Wait for the next daily quiz!",
        "wtf_usage": (
            "🤔 Usage:\n"
            "• <code>/wtf kubernetes</code> — explain a term\n"
            "• Reply to a message + <code>/wtf</code> — explain the text from that message"
        ),
        "wtf_not_configured": "⚙️ /wtf is currently unavailable (API not configured).",
        "wtf_api_error": "😵 AI is not responding right now, try again later.",
        "wtf_unexpected_error": "😵 Something went wrong, try again later.",
        "wtf_fallback_notice": "⚠️ Gemini limit exhausted, switched to Groq.\n\n",
        "wtf_rpd_footer": "\n\n---\n📊 Gemini RPD: {remaining}/{total}",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda is not configured.",
        "genquiz_usage": "❌ Usage: /genquiz &lt;topic&gt; &lt;lang&gt; &lt;difficulty&gt;",
        "genquiz_invalid_lang": "❌ Invalid lang. Choose from: {langs}",
        "genquiz_invalid_difficulty": "❌ Invalid difficulty. Choose from: {difficulties}",
        "genquiz_failed": "❌ Failed to generate quiz: {reason}",
    },
    "kk": {
        "start_message": (
            "👋 <b>Сәлем! Мен Zerde — IT қауымдастығына арналған ақылды көмекшімін.</b> 🤖\n\n"
            "Менің негізгі міндетім — чатты спам-боттардан қорғау және пайдалы статистика жинау.\n\n"
            "🚀 <b>Жұмысты қалай бастауға болады?</b>\n"
            "1. Мені өз тобыңызға қосыңыз.\n"
            "2. Маған <b>Админ</b> құқығын беріңіз.\n\n"
            "<i>Толық ақпарат алу үшін /help пәрменін жіберіңіз.</i>\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "help_message": (
            "🤖 <b>Zerde Bot: Пайдалану нұсқаулығы</b>\n\n"
            "Бұл бот топтарда автоматты түрде жұмыс істеуге арналған.\n\n"
            "🛡️ <b>Жаңа мүшелерге арналған (Анти-спам):</b>\n"
            "Топқа қосылған кезде арнайы <b>«Мен адаммын»</b> түймесін басу қажет.\n"
            "⚠️ <i>Ескерту: Түйме 60 секунд ішінде басылмаса, сіз топтан автоматты түрде шығарыласыз.</i>\n\n"
            "📊 <b>Админдер үшін:</b>\n"
            "• /stats — Топтың статистикасын және белсенділігін көру.\n"
            "• /start — Ботты қайта іске қосу (қатып қалған жағдайда).\n\n"
            "⚙️ <b>Орнату:</b>\n"
            "Бот дұрыс жұмыс істеуі үшін, оған <i>«Delete Messages»</i> "
            "және <i>«Ban Users»</i> құқықтары берілуі керек.\n\n"
            "👨‍💻 <b>Қолдау қызметі:</b>\n"
            "/support — Қате туралы хабарлау немесе ұсыныс жіберу."
        ),
        "stats_message": (
            "📊 <b>Топ статистикасы</b>\n"
            "⏰ <b></b> {start_date} бері\n\n"
            "👥 <b>Қосылған қолданушылар:</b> {total} адам\n"
            "✅ <b>Расталған мүшелер:</b> {verified} адам\n"
            "🔫 <b>Дауыс беру арқылы бұғатталғандар:</b> {banned} адам\n\n"
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
            "👋 Қош келдіңіз, {MENTION}!\n\n"
            "Топтың қауіпсіздігін қамтамасыз ету үшін, бот емес екеніңізді растаңыз.\n\n"
            "⏳ <b>Уақыт шектеулі: 60 секунд</b>\n\n"
            "(Уақыт біткен жағдайда, топтан автоматты түрде шығарыласыз)"
        ),
        "welcome_verified": (
            "{MENTION} 👋\n\n"
            "Қазақша IT қауымдастыққа қош келдіңіз! "
            "Жаңа идеялар мен жетістіктерге бірге жетейік. 🌟"
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
        "only_user_may_verify": "❌ Бұл түймені тек жаңадан қосылған қолданушы ғана баса алады.",
        "voteban_usage": "❌ Қолданылуы: Қолданушыны бұғаттау үшін, оның хабарламасына жауап (reply) ретінде /voteban пәрменін жіберіңіз.",  # noqa: E501
        "voteban_self": "❌ Өзіңізді бұғаттауға дауыс бере алмайсыз.",
        "voteban_admin": "❌ Әкімшілерді (админдерді) бұғаттауға дауыс бере алмайсыз.",
        "not_in_group": "❌ Сіз топ қосылған жоқсыз. Бұл бот топтан тыс мүшелер үшін қызмет көрсетпейді.",
        "voteban_initiated": (
            "🗳️ <b>Бұғаттауға дауыс беру</b>\n\n" "👤 Бастаған: {INITIATOR}\n" "🎯 Бұғатталатын қолданушы: {TARGET}"
        ),
        "voteban_vote_recorded": "✅ Сіздің дауысыңыз қабылданды.",
        "voteban_already_voted": "⚠️ Сіз бұл қолданушыны бұғаттауға дауыс беріп қойғансыз.",
        "voteban_banned": (
            "⚖️ <b>Дауыс беру арқылы бұғаттау</b>\n\n"
            "🎯 {TARGET} қажетті {VOTES_FOR} дауыс жинап, топтан шығарылды.\n\n"
            "🔫 Бұғаттауды қолдағандар: {VOTERS_FOR}"
        ),
        "voteban_forgiven": (
            "💚 <b>Бұғаттаудан бас тартылды</b>\n\n"
            "🎯 {TARGET} {VOTES_AGAINST} дауыспен ақталды.\n\n"
            "👼 Ақтап шыққандар (қарсы дауыс бергендер): {VOTERS_AGAINST}"
        ),
        "quizstats_response": (
            "🧠 <b>Сіздің Quiz бойынша нәтижеңіз:</b>\n\n"
            "🏆 Жалпы ұпай: <b>{score}</b>\n"
            "🔥 Үздіксіз streak: <b>{streak}</b> күн\n"
            "⭐ Ең ұзақ streak: <b>{best_streak}</b> күн\n"
            "📊 Рейтингтегі орныңыз: <b>#{rank}</b> / {total_players} қатысушы"
        ),
        "quizstats_no_data": "🧠 Сіз әлі ешқандай Quiz сұрағына жауап бермепсіз. Келесі сұрақты жіберіп алмаңыз!",
        "wtf_usage": (
            "🤔 Қолданылуы:\n"
            "• <code>/wtf kubernetes</code> — терминді түсіндіру\n"
            "• Хабарламаға жауап + <code>/wtf</code> — сол хабарламадағы мәтінді түсіндіру"
        ),
        "wtf_not_configured": "⚙️ /wtf пәрмені қазір қолжетімсіз (API бапталмаған).",
        "wtf_api_error": "😵 AI қазір жауап бермей тұр, кейінірек қайталап көріңіз.",
        "wtf_unexpected_error": "😵 Белгісіз қате орын алды, кейінірек қайталап көріңіз.",
        "wtf_fallback_notice": "⚠️ Gemini лимиті аяқталды, Groq моделіне ауыстым.\n\n",
        "wtf_rpd_footer": "\n\n---\n📊 Gemini RPD: {remaining}/{total}",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda бапталмаған.",
        "genquiz_usage": "❌ Қолданылуы: /genquiz &lt;тақырып&gt; &lt;тіл&gt; &lt;деңгей&gt;",
        "genquiz_invalid_lang": "❌ Тіл қате. Келесілерді таңдаңыз: {langs}",
        "genquiz_invalid_difficulty": "❌ Деңгей қате. Келесілерді таңдаңыз: {difficulties}",
        "genquiz_failed": "❌ Quiz жасау мүмкін болмады: {reason}",
    },
}


def get_translated_text(key: str, lang_code: str = "kk", **kwargs: Any) -> str:
    """Get translated text for *key*, falling back to DEFAULT_LANG."""
    target_lang = lang_code if lang_code in TRANSLATIONS else DEFAULT_LANG
    text = TRANSLATIONS[target_lang].get(key, key)

    try:
        text = text.format(**kwargs)
    except KeyError as e:
        logger.warning(f"Missing format key in translation: {e}")

    return text
