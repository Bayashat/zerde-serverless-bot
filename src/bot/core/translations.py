"""Localised UI strings for the Telegram bot."""

from typing import Any

from core.config import DEFAULT_LANG
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

TRANSLATIONS = {
    "en": {
        "quiz_reconcile_usage": "Reply to this bot's quiz: /quizreconcile &lt;request_key&gt; &lt;generation&gt;",
        "quiz_reconcile_admin": "Only a current group administrator can reconcile a quiz.",
        "quiz_reconcile_ok": "The existing quiz has been verified and its scoring record restored.",
        "quiz_reconcile_unknown": "The quiz is not confirmed. Check the delivery record before trying again.",
        "legacy_agent_retired": (
            "Automatic participation is retired. /ask, direct mentions and requested replies remain "
            "available. Use /memory to view, correct or forget current memory."
        ),
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
            "📜 <b>Commands:</b>\n"
            "• /start — Start or restart the bot.\n"
            "• /help — Show this guide.\n"
            "• /support — Contact support.\n"
            "• /ping — Health check.\n"
            "• /stats — Group stats (admins).\n"
            "• /memory on|off|status|forget me|forget group — Manage group memory.\n"
            "• /agent — Explain retired automatic participation.\n"
            "• /ask — Ask the agent, or reply to a message with /ask.\n"
            "• /voteban — Start vote-ban by replying to a user's message.\n"
            "• /quizstats — Show your quiz stats in DM.\n"
            "• /genquiz — Generate quiz on demand (ADMIN_USER_ID only).\n"
            "\n"
            "🛡️ <b>For New Members (Anti-Spam):</b>\n"
            "Upon joining, you must click the <b>'I am human'</b> button.\n"
            "⚠️ <i>Warning: If the button is not clicked within 60 seconds, you will be automatically removed.</i>\n\n"
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
            "🔫 <b>Banned by vote:</b> {banned} users\n"
            "🤖 <b>Banned by anti-spam:</b> {spam_banned} users\n\n"
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
        "voteban_closed": "This vote has ended.",
        "voteban_expired": (
            "This vote is expired or belongs to an older session. Start a new /voteban command if " "needed."
        ),
        "voteban_retry": "Vote processing could not finish. Retry the button or /voteban command.",
        "voteban_unconfirmed": (
            "⚠️ The vote for {TARGET} ended without a confirmed ban. An administrator must check the "
            "result; use a new /voteban for a new decision."
        ),
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
            "🧠 <b>Your Quiz Stats</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🗓 This week: <b>{week_score} pts</b> · Rank <b>#{rank}</b> / {total_players} players\n"
            "🎖 This season weekly wins: <b>{season_wins}/4</b>\n"
            "🏆 All-time season titles: <b>{season_champion_count}</b>\n"
            "──────────────\n"
            "⭐ All-time: <b>{total_score} pts</b>\n"
            "🔥 Streak: <b>{streak}</b> days current · <b>{best_streak}</b> days best"
        ),
        "quizstats_no_data": "🧠 No quiz score yet — answer tomorrow's daily quiz to get on the board!",
        "quizstats_open_private_chat": (
            "📬 I couldn't send you a private message.\n"
            "Please open a chat with me and send /start first, then try /quizstats again."
        ),
        "quiz_not_configured": "⚙️ Quiz is not configured for this bot.",
        "agent_usage": (
            "Automatic participation is retired. /ask, direct mentions and requested replies remain "
            "available. Use /memory to view, correct or forget current memory."
        ),
        "memory_storage_not_configured": "⚙️ Group memory storage is not configured for this deployment.",
        "status_on": "on",
        "status_off": "off",
        "bot_owner_only": "❌ Only the bot owner can do that.",
        "ask_usage": ("💬 Usage: <code>/ask question</code> or reply to a message/media with <code>/ask</code>."),
        "ask_agent_unavailable": "😵 The AI agent is not available right now.",
        "ask_multimodal_unavailable": "😵 Media understanding is not available right now.",
        "ask_media_unsupported": (
            "I can read images, videos, voice/audio, PDFs, and text/code/log files when explicitly asked, "
            "but not this media type yet."
        ),
        "ask_media_too_large": "I could not read this media because it is too large.",
        "ask_media_unavailable": "I could not read this media. It may be unavailable, expired, or not downloadable.",
        "ask_daily_quota_exhausted": "⚠️ AI daily quota is exhausted for today.",
        "why_reply_missing": "🤷 I do not have a recorded reason for that reply.",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda is not configured.",
        "genquiz_usage": (
            "❌ Usage: /genquiz &lt;topic&gt; [&lt;difficulty&gt; [&lt;lang&gt;]]\n"
            "Order: topic → difficulty → language.\n"
            "Difficulties: <code>easy</code>, <code>medium</code>, <code>hard</code>, <code>expert</code>.\n"
            "Defaults: difficulty <code>medium</code>, language from this group's default."
        ),
        "genquiz_invalid_lang": "❌ Invalid lang. Choose from: {langs}",
        "genquiz_invalid_difficulty": "❌ Invalid difficulty. Choose from: {difficulties}",
        "genquiz_failed": "❌ Failed to generate quiz: {reason}",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "spam_enforced_notice": "🚫 Spam detected: {REASON}. {TARGET} was removed.",
        "spam_guest_review_notice": "⚠️ Guest bot {BOT} returned suspected spam: {REASON} ({CONFIDENCE}%). Caller: {TARGET}. Calling a bot alone does not prove intent. Admins: confirm abuse before permanently banning the caller.",  # noqa: E501
        "spam_uncertain_notice": (
            "⚠️ Suspicious message from {TARGET}: {REASON} ({CONFIDENCE}% confidence). Admins please check."
        ),
        "spam_reason_job_offer": "job/income offer",
        "spam_reason_dm_redirect_scam": "DM redirect scam",
        "spam_reason_vpn_ad": "VPN advertisement",
        "spam_reason_referral_promo": "referral/promotional link",
        "spam_reason_selling_services": "selling digital services",
        "spam_reason_account_sale": "account/access sale",
        "spam_reason_crypto_investment": "crypto/investment promotion",
        "spam_reason_phishing": "phishing or malware",
        "spam_reason_adult_gambling": "adult/gambling promotion",
        "spam_reason_commercial": "commercial/promotional content",
        "spam_reason_suspicious_link": "suspicious link",
        "spam_reason_admin_review": "admin-reviewed spam",
        "spam_reason_rules": "matched spam rules",
        "spam_reason_unknown": "unknown reason",
        "spam_review_ban_button": "Ban",
        "spam_review_ignore_button": "Ignore",
        "spam_review_admin_only": "Only group admins can review spam alerts.",
        "spam_review_action_failed": "Ban not confirmed. Check bot permissions and the user status, then retry.",
        "spam_review_banned_toast": "User banned.",
        "spam_review_ignored_toast": "Alert ignored.",
        "spam_review_banned_notice": "✅ Admin reviewed this alert and banned the user.",
        "spam_review_ignored_notice": "✅ Admin reviewed this alert and ignored it.",
        "captcha_image_challenge": (
            "👋 Welcome {MENTION}!\n\n"
            "Look at the image and type the <b>4 highlighted numbers</b> in order ①②③④.\n\n"
            "⏳ Time limit: {TIMEOUT}s\n"
            "(Auto-removed if you don't verify)"
        ),
        "captcha_wrong_answer": "❌ Wrong code. <b>{ATTEMPTS_LEFT}</b> attempt(s) left.",
        "captcha_failed_kicked": "🚫 Too many wrong attempts. You have been removed.",
    },
    "kk": {
        "quiz_reconcile_usage": (
            "Осы боттың викторинасына жауап беріңіз: " "/quizreconcile &lt;request_key&gt; &lt;generation&gt;"
        ),
        "quiz_reconcile_admin": "Викторинаны тек топтың қазіргі әкімшісі растай алады.",
        "quiz_reconcile_ok": "Бар викторина расталды, ұпай санау жазбасы қалпына келтірілді.",
        "quiz_reconcile_unknown": "Викторина расталмады. Қайта әрекеттенбес бұрын жіберу жазбасын тексеріңіз.",
        "legacy_agent_retired": (
            "Автоматты түрде әңгімеге қосылу тоқтатылған. /ask, тікелей атау және ботқа жауап беру "
            "қолжетімді. Қазіргі жадты көру, түзету немесе өшіру үшін /memory пайдаланыңыз."
        ),
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
            "📜 <b>Пәрмендер:</b>\n"
            "• /start — Ботты іске қосу немесе қайта іске қосу.\n"
            "• /help — Осы нұсқаулықты көрсету.\n"
            "• /support — Қолдау қызметіне жазу.\n"
            "• /ping — Тексеру пәрмені.\n"
            "• /stats — Топ статистикасы (админдер).\n"
            "• /memory on|off|status|forget me|forget group — Топ жадын басқару.\n"
            "• /agent — Автоматты қатысудың тоқтатылғаны туралы ақпарат.\n"
            "• /ask — Agent-тен сұрау немесе хабарламаға reply жасап сұрау.\n"
            "• /voteban — Reply арқылы бұғаттауға дауыс ашу.\n"
            "• /quizstats — Quiz статистикасын жеке чатта көрсету.\n"
            "• /genquiz — Сұраныс бойынша quiz жасау (тек ADMIN_USER_ID).\n"
            "\n"
            "🛡️ <b>Жаңа мүшелерге арналған (Анти-спам):</b>\n"
            "Топқа қосылған кезде арнайы <b>«Мен адаммын»</b> түймесін басу қажет.\n"
            "⚠️ <i>Ескерту: Түйме 60 секунд ішінде басылмаса, сіз топтан автоматты түрде шығарыласыз.</i>\n\n"
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
            "✅ <b>Расталғандар:</b> {verified} адам\n"
            "🔫 <b>Дауыс беру арқылы бұғатталғандар:</b> {banned} адам\n"
            "🤖 <b>Антиспам арқылы бұғатталғандар:</b> {spam_banned} адам\n\n"
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
        "voteban_closed": "Бұл дауыс беру аяқталды.",
        "voteban_expired": (
            "Бұл дауыс беру аяқталған немесе ескі сессияға тиесілі. Қажет болса, жаңа /voteban " "бастаңыз."
        ),
        "voteban_retry": "Дауыс беруді өңдеу аяқталмады. Батырманы немесе /voteban пәрменін қайталаңыз.",
        "voteban_unconfirmed": (
            "⚠️ {TARGET} туралы дауыс беру аяқталды, бірақ бұғаттау расталмады. Әкімші нәтижені "
            "тексеруі керек; жаңа шешім үшін жаңа /voteban бастаңыз."
        ),
        "voteban_banned": (
            "⚖️ <b>Дауыс беру арқылы бұғаттау</b>\n\n"
            "🎯 {TARGET} қажетті {VOTES_FOR} дауыс жинап, топтан шығарылды.\n\n"
            "🔫 Бұғаттауды қолдағандар: {VOTERS_FOR}"
        ),
        "voteban_forgiven": (
            "💚 <b>Бұғаттаудан бас тартылды</b>\n\n"
            "🎯 {TARGET} {VOTES_AGAINST} дауыспен ақталды.\n\n"
            "👼 Ақтап шыққандар: {VOTERS_AGAINST}"
        ),
        "quizstats_response": (
            "🧠 <b>Сіздің Quiz статистикаңыз</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🗓 Осы аптада: <b>{week_score} ұпай</b> · Рейтинг <b>#{rank}</b> / {total_players} қатысушы\n"
            "🎖 Осы маусымда апталық жеңістер: <b>{season_wins}/4</b>\n"
            "🏆 Барлық уақытта маусым чемпиондығы: <b>{season_champion_count}</b>\n"
            "──────────────\n"
            "⭐ Барлық уақыт бойынша: <b>{total_score} ұпай</b>\n"
            "🔥 Серия (Streak): қазір <b>{streak}</b> күн · рекорд <b>{best_streak}</b> күн"
        ),
        "quizstats_no_data": "🧠 Сіздің ұпайыңыз әлі жоқ — ертеңгі күнделікті сұраққа жауап беріп, рейтингке кіріңіз!",
        "quizstats_open_private_chat": (
            "📬 Сізге жеке хабарлама жібере алмадым.\n"
            "Алдымен менімен жеке чат ашып, /start пәрменін жіберіңіз, содан соң /quizstats қайта көріңіз."
        ),
        "quiz_not_configured": "⚙️ Quiz бұл бот үшін бапталмаған.",
        "agent_usage": (
            "Автоматты түрде әңгімеге қосылу тоқтатылған. /ask, тікелей атау және ботқа жауап беру "
            "қолжетімді. Қазіргі жадты көру, түзету немесе өшіру үшін /memory пайдаланыңыз."
        ),
        "memory_storage_not_configured": "⚙️ Бұл deployment үшін топ жады қоймасы бапталмаған.",
        "status_on": "қосулы",
        "status_off": "өшірулі",
        "bot_owner_only": "❌ Мұны тек bot owner істей алады.",
        "ask_usage": (
            "💬 Қолданылуы: <code>/ask сұрақ</code> немесе хабарлама/медиаға reply жасап "
            "<code>/ask</code> жіберіңіз."
        ),
        "ask_agent_unavailable": "😵 AI agent қазір қолжетімсіз.",
        "ask_multimodal_unavailable": "😵 Медиа түсіну қазір қолжетімсіз.",
        "ask_media_unsupported": (
            "Нақты сұрағанда мен сурет, видео, voice/audio, PDF және text/code/log файлдарын оқи аламын, "
            "бірақ бұл медиа түрі әзірше қолдау таппайды."
        ),
        "ask_media_too_large": "Бұл медианы оқи алмадым: файл тым үлкен.",
        "ask_media_unavailable": (
            "Бұл медианы оқи алмадым. Ол қолжетімсіз, мерзімі өткен немесе жүктелмейтін болуы мүмкін."
        ),
        "ask_daily_quota_exhausted": "⚠️ Бүгінгі AI күндік лимиті таусылды.",
        "why_reply_missing": "🤷 Бұл жауап үшін жазылған себеп табылмады.",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda бапталмаған.",
        "genquiz_usage": (
            "❌ Қолданылуы: /genquiz &lt;тақырып&gt; [&lt;деңгей&gt; [&lt;тіл&gt;]]\n"
            "Реті: тақырып → деңгей → тіл.\n"
            "Деңгейлер: <code>easy</code>, <code>medium</code>, <code>hard</code>, <code>expert</code>.\n"
            "Әдепкі: деңгей <code>medium</code>, тіл осы топтың негізгі тілі бойынша."
        ),
        "genquiz_invalid_lang": "❌ Тіл қате. Келесілерді таңдаңыз: {langs}",
        "genquiz_invalid_difficulty": "❌ Деңгей қате. Келесілерді таңдаңыз: {difficulties}",
        "genquiz_failed": "❌ Quiz жасау мүмкін болмады: {reason}",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "spam_enforced_notice": "🚫 Спам анықталды: {REASON}. {TARGET} топтан шығарылды.",
        "spam_guest_review_notice": "⚠️ Қонақ бот {BOT} күдікті спам жіберді: {REASON} ({CONFIDENCE}%). Шақырған: {TARGET}. Ботты шақыру қасақана әрекетті дәлелдемейді. Мәңгі бұғаттамас бұрын админ тексерсін.",  # noqa: E501
        "spam_uncertain_notice": (
            "⚠️ {TARGET} пайдаланушыдан күдікті хабарлама: {REASON} ({CONFIDENCE}% сенімділік). Админдер тексерсін."  # noqa: E501
        ),
        "spam_reason_job_offer": "жұмыс/табыс ұсынысы",
        "spam_reason_dm_redirect_scam": "жеке хабарламаға тартатын алаяқтық",
        "spam_reason_vpn_ad": "VPN жарнамасы",
        "spam_reason_referral_promo": "реферал/жарнама сілтемесі",
        "spam_reason_selling_services": "цифрлық қызметтерді сату",
        "spam_reason_account_sale": "аккаунт/қолжетімділік сату",
        "spam_reason_crypto_investment": "крипто/инвестиция жарнамасы",
        "spam_reason_phishing": "фишинг немесе зиянды сілтеме",
        "spam_reason_adult_gambling": "ересектер/құмар ойын жарнамасы",
        "spam_reason_commercial": "коммерциялық/жарнама мазмұны",
        "spam_reason_suspicious_link": "күдікті сілтеме",
        "spam_reason_admin_review": "админ тексерген спам",
        "spam_reason_rules": "спам ережелеріне сәйкес",
        "spam_reason_unknown": "себебі белгісіз",
        "spam_review_ban_button": "Бан",
        "spam_review_ignore_button": "Елемеу",
        "spam_review_admin_only": "Спам ескертулерін тек топ админдері тексере алады.",
        "spam_review_action_failed": (
            "Бұғаттау расталмады. Бот құқықтары мен пайдаланушы күйін тексеріп, қайта көріңіз."
        ),
        "spam_review_banned_toast": "Пайдаланушы бұғатталды.",
        "spam_review_ignored_toast": "Ескерту еленбеді.",
        "spam_review_banned_notice": "✅ Админ бұл ескертуді тексеріп, пайдаланушыны бұғаттады.",
        "spam_review_ignored_notice": "✅ Админ бұл ескертуді тексеріп, елемеді.",
        "captcha_image_challenge": (
            "👋 Қош келдіңіз, {MENTION}!\n\n"
            "Суреттегі <b>①②③④ белгіленген 4 санды</b> кезегімен жазыңыз.\n\n"
            "⏳ Уақыт: {TIMEOUT} секунд\n"
            "(Уақыт өтсе, топтан шығарыласыз)"
        ),
        "captcha_wrong_answer": "❌ Қате код. <b>{ATTEMPTS_LEFT}</b> мүмкіндік қалды.",
        "captcha_failed_kicked": "🚫 Тым көп қате енгізілді. Топтан шығарылдыңыз.",
    },
    "zh": {
        "quiz_reconcile_usage": "回复此 bot 已发出的题目：/quizreconcile &lt;request_key&gt; &lt;generation&gt;",
        "quiz_reconcile_admin": "只有当前群管理员可以核对并恢复题目记录。",
        "quiz_reconcile_ok": "已核对现有题目并恢复其计分记录。",
        "quiz_reconcile_unknown": "题目尚未核实，请先检查发送记录再重试。",
        "legacy_agent_retired": "自动插话功能已退役。/ask、直接提及和明确回复 bot 仍然可用。查看、更正或遗忘当前记忆请使用 /memory。",
        "start_message": (
            "👋 <b>你好！我是 Zerde —— 面向 IT 社群的智能助手。</b> 🤖\n\n"
            "我的主要职责是保护群聊免受垃圾机器人干扰，并收集有价值的统计数据。\n\n"
            "🚀 <b>如何开始？</b>\n"
            "1. 把我添加到你的群组。\n"
            "2. 将我提升为<b>管理员</b>。\n\n"
            "<i>完整说明请发送 /help。</i>\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "help_message": (
            "🤖 <b>Zerde Bot：使用指南</b>\n\n"
            "该机器人会在群组中自动工作。\n\n"
            "📜 <b>命令列表：</b>\n"
            "• /start — 启动或重启机器人。\n"
            "• /help — 显示本指南。\n"
            "• /support — 联系支持。\n"
            "• /ping — 健康检查。\n"
            "• /stats — 查看群统计（管理员）。\n"
            "• /memory on|off|status|forget me|forget group — 管理群记忆。\n"
            "• /agent — 查看自动互动退役说明。\n"
            "• /ask — 向 agent 提问，也可回复消息提问。\n"
            "• /voteban — 回复某条消息发起封禁投票。\n"
            "• /quizstats — 在私聊查看你的 Quiz 统计。\n"
            "• /genquiz — 按需生成 Quiz（仅 ADMIN_USER_ID）。\n"
            "\n"
            "🛡️ <b>新成员（反垃圾）</b>\n"
            "入群后，请点击 <b>“我是人类”</b> 按钮。\n"
            "⚠️ <i>注意：若 60 秒内未点击，将被自动移出群组。</i>\n\n"
            "⚙️ <b>配置：</b>\n"
            "机器人正常工作需要授予 <i>“删除消息”</i> 和 <i>“封禁用户”</i> 权限。\n\n"
            "👨‍💻 <b>支持：</b>\n"
            "/support — 反馈 Bug 或功能建议。"
        ),
        "stats_message": (
            "📊 <b>群组统计</b>\n"
            "⏰ 自 {start_date} 起\n\n"
            "👥 <b>总入群：</b> {total} 人\n"
            "✅ <b>验证通过：</b> {verified} 次\n"
            "🔫 <b>投票封禁：</b> {banned} 人\n"
            "🤖 <b>反垃圾封禁：</b> {spam_banned} 人\n\n"
            "📈 <b>整体活跃度：</b> {activity_level}"
        ),
        "private_message": (
            "👋 <b>你好！我是 Zerde —— 面向 IT 社群的智能助手。</b> 🤖\n\n"
            "我的主要职责是保护群聊免受垃圾机器人干扰，并收集有价值的统计数据。\n\n"
            "⚠️ <b>该机器人仅在群聊/群组中工作。"
            "如果你想添加到你的群，请联系 <i>@bayashat</i>！</b>\n\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "support_message": "👨‍💻 技术支持\n问题请联系：<i>@bayashat</i>",
        "welcome_verification": (
            "👋 欢迎 {MENTION}！\n\n"
            "为保障群组质量，请先验证你不是机器人。\n\n"
            "⏳ <b>时限：60 秒</b>\n\n"
            "（超时将自动移出）"
        ),
        "welcome_verified": "你好 {MENTION}！欢迎来到哈萨克斯坦 IT 社群！",
        "verification_successful": "✅ 验证成功！",
        "activity_low": "🌱 低",
        "activity_medium": "🌿 中",
        "activity_high": "🔥 高",
        "error_occurred": "❌ 出现错误，请稍后重试。",
        "unknown_action": "❌ 未知操作。",
        "invalid_data": "❌ 无效数据。",
        "stats_admin_only": "❌ 只有管理员可使用 /stats。",
        "stats_error": "❌ 读取统计失败。",
        "only_user_may_verify": "❌ 只有新加入的用户本人可以验证。",
        "voteban_usage": "❌ 用法：回复某条消息并发送 /voteban，发起封禁投票。",
        "voteban_self": "❌ 你不能给自己投封禁票。",
        "voteban_admin": "❌ 你不能对管理员发起封禁投票。",
        "not_in_group": "❌ 你不在该群组中。该机器人不支持群外使用。",
        "voteban_initiated": ("🗳️ <b>封禁投票</b>\n\n" "👤 发起人：{INITIATOR}\n" "🎯 目标：{TARGET}"),
        "voteban_vote_recorded": "✅ 你的投票已记录。",
        "voteban_already_voted": "⚠️ 你已参与过本次投票。",
        "voteban_closed": "本次投票已结束。",
        "voteban_expired": "本次投票已过期或按钮属于旧会话。如有需要，请重新发起 /voteban。",
        "voteban_retry": "投票处理暂未完成。请重试按钮或 /voteban 命令以恢复处理。",
        "voteban_unconfirmed": "⚠️ 针对 {TARGET} 的投票已结束，但封禁结果未经确认。请管理员核查；如需重新决策，请发起新的 /voteban。",
        "voteban_banned": (
            "⚖️ <b>用户已被投票封禁</b>\n\n"
            "🎯 {TARGET} 获得 {VOTES_FOR} 票后已被封禁。\n\n"
            "🔫 支持封禁：{VOTERS_FOR}"
        ),
        "voteban_forgiven": (
            "💚 <b>封禁投票已取消</b>\n\n"
            "🎯 {TARGET} 获得 {VOTES_AGAINST} 票反对后已被赦免。\n\n"
            "👼 反对封禁：{VOTERS_AGAINST}"
        ),
        "quizstats_response": (
            "🧠 <b>你的 Quiz 统计</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🗓 本周：<b>{week_score} 分</b> · 排名 <b>#{rank}</b> / {total_players} 人\n"
            "🎖 本赛季周冠军次数：<b>{season_wins}/4</b>\n"
            "🏆 历史赛季冠军次数：<b>{season_champion_count}</b>\n"
            "──────────────\n"
            "⭐ 历史总分：<b>{total_score} 分</b>\n"
            "🔥 连胜：当前 <b>{streak}</b> 天 · 最佳 <b>{best_streak}</b> 天"
        ),
        "quizstats_no_data": "🧠 暂无积分记录 —— 明天参加每日测验即可上榜！",
        "quizstats_open_private_chat": (
            "📬 我无法给你发送私信。\n" "请先打开与我的私聊并发送 /start，然后再试一次 /quizstats。"
        ),
        "quiz_not_configured": "⚙️ 本机器人未配置 Quiz 功能。",
        "agent_usage": "自动插话功能已退役。/ask、直接提及和明确回复 bot 仍然可用。查看、更正或遗忘当前记忆请使用 /memory。",
        "memory_storage_not_configured": "⚙️ 当前部署未配置群记忆存储。",
        "status_on": "开启",
        "status_off": "关闭",
        "bot_owner_only": "❌ 只有 bot owner 可以这样做。",
        "ask_usage": "💬 用法：<code>/ask 问题</code>，或回复消息/媒体并发送 <code>/ask</code>。",
        "ask_agent_unavailable": "😵 AI agent 现在不可用，请稍后重试。",
        "ask_multimodal_unavailable": "😵 媒体理解功能现在不可用。",
        "ask_media_unsupported": "明确要求分析时，我可以读取图片、视频、语音/音频、PDF 和文本/代码/日志文件，但暂不支持这种媒体类型。",
        "ask_media_too_large": "我无法读取这个媒体：文件太大。",
        "ask_media_unavailable": "我无法读取这个媒体。它可能不可用、已过期，或无法下载。",
        "ask_daily_quota_exhausted": "⚠️ 今天的 AI 日配额已用完。",
        "why_reply_missing": "🤷 我没有找到那条回复的记录原因。",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda 未配置。",
        "genquiz_usage": (
            "❌ 用法：/genquiz &lt;主题&gt; [&lt;难度&gt; [&lt;语言&gt;]]\n"
            "顺序：主题 → 难度 → 语言。\n"
            "可选难度：<code>easy</code>, <code>medium</code>, <code>hard</code>, <code>expert</code>。\n"
            "默认：难度 <code>medium</code>，语言为当前群组的默认语言。"
        ),
        "genquiz_invalid_lang": "❌ 语言无效。可选：{langs}",
        "genquiz_invalid_difficulty": "❌ 难度无效。可选：{difficulties}",
        "genquiz_failed": "❌ 生成 Quiz 失败：{reason}",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD：{remaining}/{total}",
        "spam_enforced_notice": "🚫 检测到垃圾信息：{REASON}。{TARGET} 已被移出群组。",
        "spam_guest_review_notice": "⚠️ 访客机器人 {BOT} 返回疑似垃圾内容：{REASON}（{CONFIDENCE}%）。调用者：{TARGET}。调用本身不代表恶意；请管理员核查后决定是否永久封禁调用者。",  # noqa: E501
        "spam_uncertain_notice": "⚠️ 检测到来自 {TARGET} 的可疑消息：{REASON}（置信度 {CONFIDENCE}%）。请管理员核查。",
        "spam_reason_job_offer": "工作/收入邀约",
        "spam_reason_dm_redirect_scam": "私聊引流诈骗",
        "spam_reason_vpn_ad": "VPN 广告",
        "spam_reason_referral_promo": "推荐/推广链接",
        "spam_reason_selling_services": "出售数字服务",
        "spam_reason_account_sale": "出售账号/访问权限",
        "spam_reason_crypto_investment": "加密货币/投资推广",
        "spam_reason_phishing": "钓鱼或恶意链接",
        "spam_reason_adult_gambling": "成人/赌博推广",
        "spam_reason_commercial": "商业/推广内容",
        "spam_reason_suspicious_link": "可疑链接",
        "spam_reason_admin_review": "管理员确认的垃圾信息",
        "spam_reason_rules": "匹配垃圾规则",
        "spam_reason_unknown": "原因未知",
        "spam_review_ban_button": "封禁",
        "spam_review_ignore_button": "忽略",
        "spam_review_admin_only": "只有群管理员可以处理垃圾信息提醒。",
        "spam_review_action_failed": "尚未确认封禁成功。请检查机器人权限和用户状态后重试。",
        "spam_review_banned_toast": "用户已封禁。",
        "spam_review_ignored_toast": "已忽略。",
        "spam_review_banned_notice": "✅ 管理员已核查此提醒，并封禁了该用户。",
        "spam_review_ignored_notice": "✅ 管理员已核查此提醒，并选择忽略。",
        "captcha_image_challenge": (
            "👋 欢迎 {MENTION}！\n\n"
            "请查看图片，按顺序输入 <b>①②③④ 标记的 4 个数字</b>。\n\n"
            "⏳ 时限：{TIMEOUT}秒\n"
            "（超时将自动移出群组）"
        ),
        "captcha_wrong_answer": "❌ 验证码错误，还剩 <b>{ATTEMPTS_LEFT}</b> 次机会。",
        "captcha_failed_kicked": "🚫 错误次数过多，已将您移出群组。",
    },
    "ru": {
        "quiz_reconcile_usage": (
            "Ответьте на викторину этого бота: " "/quizreconcile &lt;request_key&gt; &lt;generation&gt;"
        ),
        "quiz_reconcile_admin": "Подтвердить викторину может только текущий администратор группы.",
        "quiz_reconcile_ok": "Существующая викторина подтверждена, запись для подсчёта баллов восстановлена.",
        "quiz_reconcile_unknown": "Викторина не подтверждена. Перед повтором проверьте запись об отправке.",
        "legacy_agent_retired": (
            "Автоматическое участие отключено. /ask, прямые упоминания и ответы боту доступны. Для "
            "просмотра, исправления или удаления текущей памяти используйте /memory."
        ),
        "start_message": (
            "👋 <b>Привет! Я Zerde — умный помощник для IT-сообществ.</b> 🤖\n\n"
            "Моя главная задача — защищать чаты от спам-ботов и собирать полезную статистику.\n\n"
            "🚀 <b>Как начать?</b>\n"
            "1. Добавьте меня в вашу группу.\n"
            "2. Выдайте мне права <b>администратора</b>.\n\n"
            "<i>Для полной информации отправьте /help.</i>\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "help_message": (
            "🤖 <b>Zerde Bot: руководство</b>\n\n"
            "Этот бот работает автоматически внутри групп.\n\n"
            "📜 <b>Команды:</b>\n"
            "• /start — запустить или перезапустить бота.\n"
            "• /help — показать эту справку.\n"
            "• /support — связаться с поддержкой.\n"
            "• /ping — проверка доступности.\n"
            "• /stats — статистика группы (для админов).\n"
            "• /memory on|off|status|forget me|forget group — управление памятью группы.\n"
            "• /agent — Информация об отключённом автоматическом участии.\n"
            "• /ask — задать вопрос agent-у или спросить ответом на сообщение.\n"
            "• /voteban — начать голосование за бан ответом на сообщение.\n"
            "• /quizstats — показать вашу Quiz-статистику в личке.\n"
            "• /genquiz — сгенерировать Quiz по запросу (только ADMIN_USER_ID).\n"
            "\n"
            "🛡️ <b>Для новых участников (антиспам):</b>\n"
            "После входа нужно нажать кнопку <b>«Я человек»</b>.\n"
            "⚠️ <i>Важно: если не нажать за 60 секунд, пользователь будет удален автоматически.</i>\n\n"
            "⚙️ <b>Настройка:</b>\n"
            "Для корректной работы боту нужны права <i>«Удалять сообщения»</i> и <i>«Банить пользователей»</i>.\n\n"
            "👨‍💻 <b>Поддержка:</b>\n"
            "/support — сообщить о баге или предложить улучшение."
        ),
        "stats_message": (
            "📊 <b>Статистика чата</b>\n"
            "⏰ С {start_date}\n\n"
            "👥 <b>Новых участников:</b> {total}\n"
            "✅ <b>Пройдено капч:</b> {verified}\n"
            "🔫 <b>Забанено голосованием:</b> {banned}\n"
            "🤖 <b>Забанено антиспамом:</b> {spam_banned}\n\n"
            "📈 <b>Общая активность:</b> {activity_level}"
        ),
        "private_message": (
            "👋 <b>Привет! Я Zerde — умный помощник для IT-сообществ.</b> 🤖\n\n"
            "Моя главная задача — защищать чаты от спам-ботов и собирать полезную статистику.\n\n"
            "⚠️ <b>Этот бот работает только в чатах/группах. "
            "Если хотите добавить меня в свою группу, напишите <i>@bayashat</i>!</b>\n\n"
            "🐍 <i>Powered by Python & AWS Serverless</i>"
        ),
        "support_message": "👨‍💻 Техподдержка\nПо вопросам: <i>@bayashat</i>",
        "welcome_verification": (
            "👋 Добро пожаловать, {MENTION}!\n\n"
            "Для безопасности группы подтвердите, что вы не бот.\n\n"
            "⏳ <b>Лимит времени: 60 секунд</b>\n\n"
            "(При таймауте пользователь будет удален автоматически)"
        ),
        "welcome_verified": "Привет, {MENTION}! Добро пожаловать в казахстанское IT-сообщество!",
        "verification_successful": "✅ Подтверждено!",
        "activity_low": "🌱 Низкая",
        "activity_medium": "🌿 Средняя",
        "activity_high": "🔥 Высокая",
        "error_occurred": "❌ Произошла ошибка. Попробуйте позже.",
        "unknown_action": "❌ Неизвестное действие.",
        "invalid_data": "❌ Некорректные данные.",
        "stats_admin_only": "❌ Команда /stats доступна только администраторам.",
        "stats_error": "❌ Не удалось загрузить статистику.",
        "only_user_may_verify": "❌ Подтвердиться может только пользователь, который вошел в группу.",
        "voteban_usage": (
            "❌ Использование: ответьте на сообщение и отправьте /voteban, " "чтобы начать голосование за бан."
        ),
        "voteban_self": "❌ Нельзя голосовать за бан самого себя.",
        "voteban_admin": "❌ Нельзя голосовать за бан администраторов.",
        "not_in_group": "❌ Вы не состоите в группе. Бот не работает вне групп.",
        "voteban_initiated": ("🗳️ <b>Голосование за бан</b>\n\n" "👤 Инициатор: {INITIATOR}\n" "🎯 Цель: {TARGET}"),
        "voteban_vote_recorded": "✅ Ваш голос учтен.",
        "voteban_already_voted": "⚠️ Вы уже голосовали в этом голосовании.",
        "voteban_closed": "Это голосование завершено.",
        "voteban_expired": (
            "Это голосование истекло или относится к старой сессии. При необходимости начните новое " "/voteban."
        ),
        "voteban_retry": (
            "Обработка голосования не завершена. Повторите кнопку или команду /voteban для " "восстановления."
        ),
        "voteban_unconfirmed": (
            "⚠️ Голосование по {TARGET} завершено без подтвержденного бана. Администратору нужно "
            "проверить результат; для нового решения начните новое /voteban."
        ),
        "voteban_banned": (
            "⚖️ <b>Пользователь забанен голосованием</b>\n\n"
            "🎯 {TARGET} был забанен после {VOTES_FOR} голосов.\n\n"
            "🔫 Голосовали за бан: {VOTERS_FOR}"
        ),
        "voteban_forgiven": (
            "💚 <b>Голосование за бан отменено</b>\n\n"
            "🎯 {TARGET} прощен при {VOTES_AGAINST} голосах против.\n\n"
            "👼 Голосовали против бана: {VOTERS_AGAINST}"
        ),
        "quizstats_response": (
            "🧠 <b>Ваша статистика Quiz</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🗓 На этой неделе: <b>{week_score} очк.</b> · Ранг <b>#{rank}</b> / {total_players} игроков\n"
            "🎖 Недельных побед в текущем сезоне: <b>{season_wins}/4</b>\n"
            "🏆 Сезонных чемпионств за всё время: <b>{season_champion_count}</b>\n"
            "──────────────\n"
            "⭐ За всё время: <b>{total_score} очк.</b>\n"
            "🔥 Серия: <b>{streak}</b> дн. сейчас · <b>{best_streak}</b> дн. рекорд"
        ),
        "quizstats_no_data": "🧠 Очков пока нет — ответьте на завтрашний ежедневный вопрос и попадите в рейтинг!",
        "quizstats_open_private_chat": (
            "📬 Я не смог отправить вам личное сообщение.\n"
            "Сначала откройте со мной личный чат и отправьте /start, затем попробуйте /quizstats снова."
        ),
        "quiz_not_configured": "⚙️ Quiz для этого бота не настроен.",
        "agent_usage": (
            "Автоматическое участие отключено. /ask, прямые упоминания и ответы боту доступны. Для "
            "просмотра, исправления или удаления текущей памяти используйте /memory."
        ),
        "memory_storage_not_configured": "⚙️ Хранилище памяти группы не настроено для этого deployment.",
        "status_on": "включено",
        "status_off": "выключено",
        "bot_owner_only": "❌ Это может делать только bot owner.",
        "ask_usage": (
            "💬 Использование: <code>/ask вопрос</code> или ответьте на сообщение/медиа командой " "<code>/ask</code>."
        ),
        "ask_agent_unavailable": "😵 AI agent сейчас недоступен.",
        "ask_multimodal_unavailable": "😵 Понимание медиа сейчас недоступно.",
        "ask_media_unsupported": (
            "По явному запросу я могу читать изображения, видео, voice/audio, PDF и text/code/log файлы, "
            "но этот тип медиа пока не поддерживается."
        ),
        "ask_media_too_large": "Я не смог прочитать это медиа: файл слишком большой.",
        "ask_media_unavailable": (
            "Я не смог прочитать это медиа. Оно может быть недоступно, просрочено или не скачиваться."
        ),
        "ask_daily_quota_exhausted": "⚠️ Дневная квота AI на сегодня исчерпана.",
        "why_reply_missing": "🤷 У меня нет записанной причины для этого ответа.",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda не настроена.",
        "genquiz_usage": (
            "❌ Использование: /genquiz &lt;тема&gt; [&lt;сложность&gt; [&lt;язык&gt;]]\n"
            "Порядок: тема → сложность → язык.\n"
            "Сложности: <code>easy</code>, <code>medium</code>, <code>hard</code>, <code>expert</code>.\n"
            "По умолчанию: сложность <code>medium</code>, язык по умолчанию для этой группы."
        ),
        "genquiz_invalid_lang": "❌ Неверный язык. Выберите из: {langs}",
        "genquiz_invalid_difficulty": "❌ Неверная сложность. Выберите из: {difficulties}",
        "genquiz_failed": "❌ Не удалось сгенерировать Quiz: {reason}",
        "genquiz_rpd_footer": "📊 Quiz Gemini RPD: {remaining}/{total}",
        "spam_enforced_notice": "🚫 Обнаружен спам: {REASON}. Пользователь {TARGET} удален из группы.",
        "spam_guest_review_notice": "⚠️ Гостевой бот {BOT} прислал подозрительный спам: {REASON} ({CONFIDENCE}%). Вызвал: {TARGET}. Сам вызов не доказывает умысел. Перед вечной блокировкой вызывавшего нужна проверка администратора.",  # noqa: E501
        "spam_uncertain_notice": (
            "⚠️ Подозрительное сообщение от {TARGET}: {REASON} ({CONFIDENCE}% уверенности). Проверьте вручную."
        ),
        "spam_reason_job_offer": "предложение работы/дохода",
        "spam_reason_dm_redirect_scam": "скам с переводом в личные сообщения",
        "spam_reason_vpn_ad": "реклама VPN",
        "spam_reason_referral_promo": "реферальная/рекламная ссылка",
        "spam_reason_selling_services": "продажа цифровых услуг",
        "spam_reason_account_sale": "продажа аккаунтов/доступа",
        "spam_reason_crypto_investment": "крипто/инвестиционная реклама",
        "spam_reason_phishing": "фишинг или вредоносная ссылка",
        "spam_reason_adult_gambling": "реклама 18+/казино/ставок",
        "spam_reason_commercial": "коммерческий/рекламный контент",
        "spam_reason_suspicious_link": "подозрительная ссылка",
        "spam_reason_admin_review": "спам, подтвержденный админом",
        "spam_reason_rules": "соответствие правилам спама",
        "spam_reason_unknown": "неизвестная причина",
        "spam_review_ban_button": "Бан",
        "spam_review_ignore_button": "Игнор",
        "spam_review_admin_only": "Проверять спам-алерты могут только админы группы.",
        "spam_review_action_failed": "Бан не подтверждён. Проверьте права бота и статус пользователя, затем повторите.",
        "spam_review_banned_toast": "Пользователь забанен.",
        "spam_review_ignored_toast": "Алерт проигнорирован.",
        "spam_review_banned_notice": "✅ Админ проверил этот алерт и забанил пользователя.",
        "spam_review_ignored_notice": "✅ Админ проверил этот алерт и проигнорировал его.",
        "captcha_image_challenge": (
            "👋 Добро пожаловать, {MENTION}!\n\n"
            "Посмотрите на изображение и введите <b>4 отмеченных числа</b> по порядку ①②③④.\n\n"
            "⏳ Лимит: {TIMEOUT}с\n"
            "(При таймауте будете удалены)"
        ),
        "captcha_wrong_answer": "❌ Неверный код. Осталось попыток: <b>{ATTEMPTS_LEFT}</b>.",
        "captcha_failed_kicked": "🚫 Слишком много неверных попыток. Вы удалены.",
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
