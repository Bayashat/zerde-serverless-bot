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
            "📜 <b>Commands:</b>\n"
            "• /start — Start or restart the bot.\n"
            "• /help — Show this guide.\n"
            "• /support — Contact support.\n"
            "• /ping — Health check.\n"
            "• /stats — Group stats (admins).\n"
            "• /memory on|off|status|forget me|forget group — Manage group memory.\n"
            "• /agent on|off|status|why — Manage agent participation.\n"
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
        "memory_usage": (
            "🧠 <b>Group memory</b>\n\n"
            "• <code>/memory on</code> — enable group memory\n"
            "• <code>/memory off</code> — disable memory and agent\n"
            "• <code>/memory status</code> — show memory status\n"
            "• <code>/memory about me</code> — show what I know from your own messages\n"
            "• <code>/memory forget me</code> — delete your memory in this group\n"
            "• <code>/memory forget this</code> — reply to a bot answer or source message and delete related memory\n"
            "• <code>/memory wrong</code> — reply to a bot answer and mark its memory sources as wrong\n"
            "• <code>/memory forget group</code> — delete all group memory"
        ),
        "agent_usage": (
            "🤖 <b>Agent mode</b>\n\n"
            "• <code>/agent on</code> — let me answer and occasionally join in\n"
            "• <code>/agent off</code> — stop proactive, mention, and reply-thread participation\n"
            "• <code>/agent status</code> — show agent and memory status\n"
            "• <code>/agent why</code> — explain why I replied\n"
            "• <code>/agent wrong</code> — reply to my answer and down-rank wrong memory sources"
        ),
        "memory_storage_not_configured": "⚙️ Group memory storage is not configured for this deployment.",
        "memory_deployment_disabled": "⚙️ Group memory is disabled by deployment config.",
        "agent_deployment_disabled": "⚙️ The group agent is disabled by deployment config.",
        "status_on": "on",
        "status_off": "off",
        "memory_owner_only": "❌ Only the group owner or bot owner can change group memory settings.",
        "bot_owner_only": "❌ Only the bot owner can do that.",
        "memory_enabled": "🧠 Group memory is now on. I will remember recent non-command messages for context.",
        "memory_disabled": (
            "🧠 Group memory is now off. Existing stored memory is kept until TTL or /memory forget group."
        ),
        "agent_enabled": "🤖 Group agent is now on. I can answer when asked and join in when it is useful.",
        "agent_disabled": (
            "🤖 Agent participation is disabled.\n"
            "I will not proactively join conversations or respond to mentions/replies.\n"
            "Explicit /ask remains available while memory is enabled."
        ),
        "memory_status_message": (
            "🧠 <b>Group memory:</b> {memory}\n"
            "🤖 <b>Group agent:</b> {agent}\n"
            "💬 <b>Recent messages:</b> {recent_messages}\n"
            "👥 <b>User profiles:</b> {user_profiles}\n"
            "📚 <b>Long-term memory:</b> {events} events, {user_facts} user facts, "
            "{group_facts} group facts, {jokes} jokes\n"
            "🗓 <b>Daily summaries:</b> {daily_summaries}\n"
            "🔎 <b>Vector memory:</b> configured {vector_configured}, indexed {vector_indexed}/{vector_total}, "
            "pending {vector_pending}, failed {vector_failed}, skipped {vector_skipped}\n"
            "🧵 <b>Vector backfill:</b> {vector_backfill}\n"
            "🧾 <b>Recorded agent replies:</b> {agent_replies}"
        ),
        "ask_usage": ("💬 Usage: <code>/ask question</code> or reply to a message/media with <code>/ask</code>."),
        "ask_memory_off": "🧠 Group memory is off. Ask the group owner to run <code>/memory on</code> first.",
        "ask_agent_unavailable": "😵 The AI agent is not available right now.",
        "ask_multimodal_unavailable": "😵 Media understanding is not available right now.",
        "ask_media_unsupported": (
            "I can read images, voice/audio, PDFs, and text/code/log files through /ask, "
            "but not this media type yet."
        ),
        "ask_media_too_large": "I could not read this media because it is too large.",
        "ask_media_unavailable": "I could not read this media. It may be unavailable, expired, or not downloadable.",
        "ask_daily_quota_exhausted": "⚠️ AI daily quota is exhausted for today.",
        "forget_group_done": "🧹 Deleted {deleted} memory items for this group.\n{vector_note}",
        "forget_me_no_user": "❌ I could not identify your Telegram user id.",
        "forget_me_done": "🧹 Deleted {deleted} memory items linked to you in this group.\n{vector_note}",
        "memory_about_me_empty": "🧠 I do not have a stored profile for you in this group yet.",
        "memory_about_me_message": (
            "🧠 <b>I know this from your own messages:</b>\n"
            "- language style: {language_style}\n"
            "- common topics: {common_topics}\n"
            "- self-stated preferences: {preferences}\n"
            "- self-stated background: {background}\n"
            "- boundaries: {boundaries}\n\n"
            "Use <code>/memory forget me</code> to remove your stored user memory."
        ),
        "forget_this_usage": ("Reply to a bot answer or source message with <code>/memory forget this</code>."),
        "forget_this_not_allowed": (
            "❌ You can only delete memory linked to your own messages. "
            "The group owner or bot owner can delete group memory."
        ),
        "forget_this_no_sources": "🧠 That bot answer has no deletable recorded memory sources.",
        "forget_this_nothing_deleted": "🧠 I did not find stored memory for that message.",
        "forget_this_done": "🧹 Deleted {deleted} related memory item(s).\n{vector_note}",
        "wrong_memory_usage": "Reply to a bot answer with <code>/agent wrong</code> or <code>/memory wrong</code>.",
        "wrong_memory_no_sources": "🧠 That answer has no stored memory sources I can mark.",
        "wrong_memory_done": "🧠 Marked {marked} memory source(s) as wrong. I will rank them lower in future answers.",
        "vector_configured_yes": "yes",
        "vector_configured_no": "no",
        "vector_backfill_none": "-",
        "vector_backfill_queued": "queued",
        "vector_backfill_queued_next_page": "queued; more pages pending",
        "vector_backfill_queued_with_failures": "queued with failures",
        "vector_backfill_progress": (
            "processed {processed_total}, enqueued {enqueued_total}, failures {failures_total}"
        ),
        "vector_cleanup_deleted": "Vector memory cleanup requested for {deleted} indexed item(s).",
        "vector_cleanup_skipped": "Vector memory cleanup is not configured.",
        "vector_cleanup_delayed": "Vector memory cleanup was not fully confirmed; stored memory was still deleted.",
        "why_reply_missing": "🤷 I do not have a recorded reason for that reply.",
        "why_reply_message": (
            "🧾 <b>Why I replied</b>\n"
            "Reason: {reason}\n"
            "Trigger: {trigger}\n"
            "Confidence: {confidence}\n"
            "{sources}"
        ),
        "why_sources_none": "Memory sources: none recorded",
        "why_sources_header": "Memory sources:",
        "why_sources_item": "- {label}: {value}",
        "why_source_yes": "yes",
        "why_source_requester_profile": "requester profile",
        "why_source_target_profile": "target profile",
        "why_source_semantic": "semantic memory",
        "why_source_lexical": "lexical memory",
        "why_source_long_term": "long-term group memory",
        "why_source_recent": "recent context",
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
            "• /agent on|off|status|why — Agent режимін басқару.\n"
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
        "memory_usage": (
            "🧠 <b>Топ жады</b>\n\n"
            "• <code>/memory on</code> — топ жадын қосу\n"
            "• <code>/memory off</code> — жад пен agent режимін өшіру\n"
            "• <code>/memory status</code> — жад күйін көрсету\n"
            "• <code>/memory about me</code> — өз хабарламаларыңыздан не білгенімді көрсету\n"
            "• <code>/memory forget me</code> — осы топтағы өз жадыңызды өшіру\n"
            "• <code>/memory forget this</code> — bot жауабына не source хабарламаға reply жасап қатысты жадты өшіру\n"
            "• <code>/memory wrong</code> — bot жауабына reply жасап оның memory source-тарын қате деп белгілеу\n"
            "• <code>/memory forget group</code> — топтың барлық жадын өшіру"
        ),
        "agent_usage": (
            "🤖 <b>Agent режимі</b>\n\n"
            "• <code>/agent on</code> — жауап беруге және қажет жерде чатқа қосылуға рұқсат беру\n"
            "• <code>/agent off</code> — proactive, mention және reply-thread қатысуын өшіру\n"
            "• <code>/agent status</code> — agent пен жад күйін көрсету\n"
            "• <code>/agent why</code> — неге жауап бергенімді түсіндіру\n"
            "• <code>/agent wrong</code> — жауабыма reply жасап қате memory source-тарды төмендету"
        ),
        "memory_storage_not_configured": "⚙️ Бұл deployment үшін топ жады қоймасы бапталмаған.",
        "memory_deployment_disabled": "⚙️ Топ жады deployment конфигінде өшірілген.",
        "agent_deployment_disabled": "⚙️ Топ agent-і deployment конфигінде өшірілген.",
        "status_on": "қосулы",
        "status_off": "өшірулі",
        "memory_owner_only": "❌ Топ жадын тек топ иесі немесе bot owner өзгерте алады.",
        "bot_owner_only": "❌ Мұны тек bot owner істей алады.",
        "memory_enabled": "🧠 Топ жады қосылды. Контекст үшін соңғы command емес хабарламаларды есте сақтаймын.",
        "memory_disabled": "🧠 Топ жады өшірілді. Бар жад TTL біткенше немесе /memory forget group дейін сақталады.",
        "agent_enabled": "🤖 Agent режимі қосылды. Сұрағанда жауап беремін, пайдалы кезде чатқа қосыла аламын.",
        "agent_disabled": (
            "🤖 Agent қатысуы өшірілді.\n"
            "Мен proactive түрде чатқа қосылмаймын және mention/reply хабарламаларына жауап бермеймін.\n"
            "Жад қосулы болса, explicit /ask қолжетімді болып қалады."
        ),
        "memory_status_message": (
            "🧠 <b>Топ жады:</b> {memory}\n"
            "🤖 <b>Agent режимі:</b> {agent}\n"
            "💬 <b>Соңғы хабарламалар:</b> {recent_messages}\n"
            "👥 <b>Қолданушы профильдері:</b> {user_profiles}\n"
            "📚 <b>Ұзақ мерзімді жад:</b> {events} оқиға, {user_facts} қолданушы фактісі, "
            "{group_facts} топ фактісі, {jokes} әзіл\n"
            "🗓 <b>Күндік қорытындылар:</b> {daily_summaries}\n"
            "🔎 <b>Vector жады:</b> бапталған {vector_configured}, indexed {vector_indexed}/{vector_total}, "
            "pending {vector_pending}, failed {vector_failed}, skipped {vector_skipped}\n"
            "🧵 <b>Vector backfill:</b> {vector_backfill}\n"
            "🧾 <b>Жазылған agent жауаптары:</b> {agent_replies}"
        ),
        "ask_usage": (
            "💬 Қолданылуы: <code>/ask сұрақ</code> немесе хабарлама/медиаға reply жасап "
            "<code>/ask</code> жіберіңіз."
        ),
        "ask_memory_off": "🧠 Топ жады өшірулі. Топ иесінен алдымен <code>/memory on</code> жіберуді сұраңыз.",
        "ask_agent_unavailable": "😵 AI agent қазір қолжетімсіз.",
        "ask_multimodal_unavailable": "😵 Медиа түсіну қазір қолжетімсіз.",
        "ask_media_unsupported": (
            "Мен /ask арқылы сурет, voice/audio, PDF және text/code/log файлдарын оқи аламын, "
            "бірақ бұл медиа түрі әзірше қолдау таппайды."
        ),
        "ask_media_too_large": "Бұл медианы оқи алмадым: файл тым үлкен.",
        "ask_media_unavailable": (
            "Бұл медианы оқи алмадым. Ол қолжетімсіз, мерзімі өткен немесе жүктелмейтін болуы мүмкін."
        ),
        "ask_daily_quota_exhausted": "⚠️ Бүгінгі AI күндік лимиті таусылды.",
        "forget_group_done": "🧹 Бұл топ үшін {deleted} жад элементі өшірілді.\n{vector_note}",
        "forget_me_no_user": "❌ Telegram user id-іңізді анықтай алмадым.",
        "forget_me_done": "🧹 Осы топта сізге қатысты {deleted} жад элементі өшірілді.\n{vector_note}",
        "memory_about_me_empty": "🧠 Бұл топта сіз туралы сақталған профиль әлі жоқ.",
        "memory_about_me_message": (
            "🧠 <b>Өз хабарламаларыңыздан мынаны білемін:</b>\n"
            "- тіл стилі: {language_style}\n"
            "- жиі тақырыптар: {common_topics}\n"
            "- өзіңіз айтқан қалаулар: {preferences}\n"
            "- өзіңіз айтқан background: {background}\n"
            "- шекаралар: {boundaries}\n\n"
            "Сақталған user memory өшіру үшін <code>/memory forget me</code> қолданыңыз."
        ),
        "forget_this_usage": (
            "Bot жауабына немесе source хабарламаға reply жасап <code>/memory forget this</code> жіберіңіз."
        ),
        "forget_this_not_allowed": (
            "❌ Тек өз хабарламаларыңызға байланысты жадты өшіре аласыз. "
            "Топ иесі немесе bot owner group memory өшіре алады."
        ),
        "forget_this_no_sources": "🧠 Бұл bot жауабында өшіруге болатын жазылған memory source жоқ.",
        "forget_this_nothing_deleted": "🧠 Ол хабарлама үшін сақталған жад таппадым.",
        "forget_this_done": "🧹 Қатысты {deleted} жад элементі өшірілді.\n{vector_note}",
        "wrong_memory_usage": (
            "Bot жауабына reply жасап <code>/agent wrong</code> немесе <code>/memory wrong</code> жіберіңіз."
        ),
        "wrong_memory_no_sources": "🧠 Бұл жауапта белгілей алатын сақталған memory source жоқ.",
        "wrong_memory_done": "🧠 {marked} memory source қате деп белгіленді. Келесі жауаптарда төменірек ранктеледі.",
        "vector_configured_yes": "иә",
        "vector_configured_no": "жоқ",
        "vector_backfill_none": "-",
        "vector_backfill_queued": "кезекке қойылды",
        "vector_backfill_queued_next_page": "кезекке қойылды; тағы беттер бар",
        "vector_backfill_queued_with_failures": "кезекке қойылды, кейбір қате бар",
        "vector_backfill_progress": (
            "өңделді {processed_total}, кезекке қойылды {enqueued_total}, қате {failures_total}"
        ),
        "vector_cleanup_deleted": "{deleted} indexed vector жад элементін өшіру сұралды.",
        "vector_cleanup_skipped": "Vector жадын тазалау бапталмаған.",
        "vector_cleanup_delayed": "Vector жадын тазалау толық расталмады; сақталған жад бәрібір өшірілді.",
        "why_reply_missing": "🤷 Бұл жауап үшін жазылған себеп табылмады.",
        "why_reply_message": (
            "🧾 <b>Неге жауап бердім</b>\n"
            "Себеп: {reason}\n"
            "Триггер: {trigger}\n"
            "Сенімділік: {confidence}\n"
            "{sources}"
        ),
        "why_sources_none": "Memory sources: жазылмаған",
        "why_sources_header": "Memory sources:",
        "why_sources_item": "- {label}: {value}",
        "why_source_yes": "иә",
        "why_source_requester_profile": "сұраушы профилі",
        "why_source_target_profile": "нысан user профилі",
        "why_source_semantic": "semantic memory",
        "why_source_lexical": "lexical memory",
        "why_source_long_term": "ұзақ мерзімді group memory",
        "why_source_recent": "соңғы контекст",
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
            "• /agent on|off|status|why — 管理 agent 参与方式。\n"
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
        "memory_usage": (
            "🧠 <b>群记忆</b>\n\n"
            "• <code>/memory on</code> — 开启群记忆\n"
            "• <code>/memory off</code> — 关闭记忆和 agent\n"
            "• <code>/memory status</code> — 查看记忆状态\n"
            "• <code>/memory about me</code> — 查看我从你自己的消息中记住了什么\n"
            "• <code>/memory forget me</code> — 删除你在本群的记忆\n"
            "• <code>/memory forget this</code> — 回复 bot 答案或来源消息并删除相关记忆\n"
            "• <code>/memory wrong</code> — 回复 bot 答案并标记其记忆来源有误\n"
            "• <code>/memory forget group</code> — 删除整个群的记忆"
        ),
        "agent_usage": (
            "🤖 <b>Agent 模式</b>\n\n"
            "• <code>/agent on</code> — 允许我回答并在合适时加入聊天\n"
            "• <code>/agent off</code> — 关闭主动、mention 和 reply-thread 参与\n"
            "• <code>/agent status</code> — 查看 agent 和记忆状态\n"
            "• <code>/agent why</code> — 解释我为什么回复\n"
            "• <code>/agent wrong</code> — 回复我的答案并降低错误记忆来源的优先级"
        ),
        "memory_storage_not_configured": "⚙️ 当前部署未配置群记忆存储。",
        "memory_deployment_disabled": "⚙️ 群记忆已被部署配置关闭。",
        "agent_deployment_disabled": "⚙️ 群 agent 已被部署配置关闭。",
        "status_on": "开启",
        "status_off": "关闭",
        "memory_owner_only": "❌ 只有群主或 bot owner 可以修改群记忆设置。",
        "bot_owner_only": "❌ 只有 bot owner 可以这样做。",
        "memory_enabled": "🧠 群记忆已开启。我会记住近期非命令消息，用于上下文。",
        "memory_disabled": "🧠 群记忆已关闭。已有记忆会保留到 TTL 到期，或直到执行 /memory forget group。",
        "agent_enabled": "🤖 Agent 模式已开启。有人问我时我会回答，也会在有帮助的时候加入聊天。",
        "agent_disabled": (
            "🤖 Agent 参与已关闭。\n"
            "我不会主动加入对话，也不会响应 mention/reply。\n"
            "只要群记忆开启，显式 /ask 仍然可用。"
        ),
        "memory_status_message": (
            "🧠 <b>群记忆：</b>{memory}\n"
            "🤖 <b>群 agent：</b>{agent}\n"
            "💬 <b>近期消息：</b>{recent_messages}\n"
            "👥 <b>用户画像：</b>{user_profiles}\n"
            "📚 <b>长期记忆：</b>{events} 个事件，{user_facts} 条用户事实，"
            "{group_facts} 条群事实，{jokes} 个梗\n"
            "🗓 <b>每日摘要：</b>{daily_summaries}\n"
            "🔎 <b>向量记忆：</b>已配置 {vector_configured}，已索引 {vector_indexed}/{vector_total}，"
            "待处理 {vector_pending}，失败 {vector_failed}，跳过 {vector_skipped}\n"
            "🧵 <b>向量回填：</b>{vector_backfill}\n"
            "🧾 <b>已记录 agent 回复：</b>{agent_replies}"
        ),
        "ask_usage": "💬 用法：<code>/ask 问题</code>，或回复消息/媒体并发送 <code>/ask</code>。",
        "ask_memory_off": "🧠 群记忆未开启。请让群主先执行 <code>/memory on</code>。",
        "ask_agent_unavailable": "😵 AI agent 现在不可用，请稍后重试。",
        "ask_multimodal_unavailable": "😵 媒体理解功能现在不可用。",
        "ask_media_unsupported": "我可以通过 /ask 读取图片、语音/音频、PDF 和文本/代码/日志文件，但暂不支持这种媒体类型。",
        "ask_media_too_large": "我无法读取这个媒体：文件太大。",
        "ask_media_unavailable": "我无法读取这个媒体。它可能不可用、已过期，或无法下载。",
        "ask_daily_quota_exhausted": "⚠️ 今天的 AI 日配额已用完。",
        "forget_group_done": "🧹 已删除本群 {deleted} 条记忆。\n{vector_note}",
        "forget_me_no_user": "❌ 我无法识别你的 Telegram user id。",
        "forget_me_done": "🧹 已删除本群与你相关的 {deleted} 条记忆。\n{vector_note}",
        "memory_about_me_empty": "🧠 我还没有在这个群里保存你的画像。",
        "memory_about_me_message": (
            "🧠 <b>我从你自己的消息中知道这些：</b>\n"
            "- 语言风格：{language_style}\n"
            "- 常见话题：{common_topics}\n"
            "- 自述偏好：{preferences}\n"
            "- 自述背景：{background}\n"
            "- 边界：{boundaries}\n\n"
            "使用 <code>/memory forget me</code> 删除你的用户记忆。"
        ),
        "forget_this_usage": "请回复一条 bot 答案或来源消息，并发送 <code>/memory forget this</code>。",
        "forget_this_not_allowed": "❌ 你只能删除与你自己消息相关的记忆。群主或 bot owner 可以删除群记忆。",
        "forget_this_no_sources": "🧠 那条 bot 答案没有可删除的已记录记忆来源。",
        "forget_this_nothing_deleted": "🧠 我没有找到那条消息对应的已存记忆。",
        "forget_this_done": "🧹 已删除 {deleted} 条相关记忆。\n{vector_note}",
        "wrong_memory_usage": "请回复一条 bot 答案，并发送 <code>/agent wrong</code> 或 <code>/memory wrong</code>。",
        "wrong_memory_no_sources": "🧠 那条答案没有可标记的已存记忆来源。",
        "wrong_memory_done": "🧠 已标记 {marked} 条记忆来源有误。之后回答时会降低其优先级。",
        "vector_configured_yes": "是",
        "vector_configured_no": "否",
        "vector_backfill_none": "-",
        "vector_backfill_queued": "已入队",
        "vector_backfill_queued_next_page": "已入队；还有后续分页",
        "vector_backfill_queued_with_failures": "已入队，但有部分失败",
        "vector_backfill_progress": "已扫描 {processed_total}，已入队 {enqueued_total}，失败 {failures_total}",
        "vector_cleanup_deleted": "已请求删除 {deleted} 条已索引向量记忆。",
        "vector_cleanup_skipped": "未配置向量记忆清理。",
        "vector_cleanup_delayed": "向量记忆清理未完全确认；已删除存储记忆。",
        "why_reply_missing": "🤷 我没有找到那条回复的记录原因。",
        "why_reply_message": (
            "🧾 <b>我为什么回复</b>\n" "原因：{reason}\n" "触发：{trigger}\n" "置信度：{confidence}\n" "{sources}"
        ),
        "why_sources_none": "记忆来源：未记录",
        "why_sources_header": "记忆来源：",
        "why_sources_item": "- {label}: {value}",
        "why_source_yes": "是",
        "why_source_requester_profile": "提问者画像",
        "why_source_target_profile": "目标用户画像",
        "why_source_semantic": "语义记忆",
        "why_source_lexical": "词面记忆",
        "why_source_long_term": "长期群记忆",
        "why_source_recent": "近期上下文",
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
            "• /agent on|off|status|why — управление agent-режимом.\n"
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
        "memory_usage": (
            "🧠 <b>Память группы</b>\n\n"
            "• <code>/memory on</code> — включить память группы\n"
            "• <code>/memory off</code> — выключить память и agent\n"
            "• <code>/memory status</code> — показать статус памяти\n"
            "• <code>/memory about me</code> — показать, что я знаю из ваших сообщений\n"
            "• <code>/memory forget me</code> — удалить вашу память в этой группе\n"
            "• <code>/memory forget this</code> — ответьте на ответ бота или source-сообщение "
            "и удалите связанную память\n"
            "• <code>/memory wrong</code> — ответьте на ответ бота и отметьте его источники памяти как ошибочные\n"
            "• <code>/memory forget group</code> — удалить всю память группы"
        ),
        "agent_usage": (
            "🤖 <b>Agent-режим</b>\n\n"
            "• <code>/agent on</code> — разрешить мне отвечать и иногда подключаться к чату\n"
            "• <code>/agent off</code> — выключить proactive, mention и reply-thread участие\n"
            "• <code>/agent status</code> — показать статус agent-а и памяти\n"
            "• <code>/agent why</code> — объяснить, почему я ответил\n"
            "• <code>/agent wrong</code> — ответьте на мой ответ и понизьте ошибочные memory sources"
        ),
        "memory_storage_not_configured": "⚙️ Хранилище памяти группы не настроено для этого deployment.",
        "memory_deployment_disabled": "⚙️ Память группы выключена в deployment-конфиге.",
        "agent_deployment_disabled": "⚙️ Group agent выключен в deployment-конфиге.",
        "status_on": "включено",
        "status_off": "выключено",
        "memory_owner_only": "❌ Только владелец группы или bot owner может менять настройки памяти.",
        "bot_owner_only": "❌ Это может делать только bot owner.",
        "memory_enabled": "🧠 Память группы включена. Я буду помнить недавние не-command сообщения для контекста.",
        "memory_disabled": (
            "🧠 Память группы выключена. Уже сохраненная память останется до TTL или /memory forget group."
        ),
        "agent_enabled": "🤖 Agent-режим включен. Я могу отвечать по запросу и подключаться, когда это полезно.",
        "agent_disabled": (
            "🤖 Участие agent-а выключено.\n"
            "Я не буду proactive вступать в разговоры или отвечать на mentions/replies.\n"
            "Явный /ask остается доступен, пока включена память."
        ),
        "memory_status_message": (
            "🧠 <b>Память группы:</b> {memory}\n"
            "🤖 <b>Agent-режим:</b> {agent}\n"
            "💬 <b>Недавние сообщения:</b> {recent_messages}\n"
            "👥 <b>Профили пользователей:</b> {user_profiles}\n"
            "📚 <b>Долгосрочная память:</b> события {events}, факты пользователей {user_facts}, "
            "факты группы {group_facts}, шутки {jokes}\n"
            "🗓 <b>Дневные сводки:</b> {daily_summaries}\n"
            "🔎 <b>Векторная память:</b> настроена {vector_configured}, indexed {vector_indexed}/{vector_total}, "
            "pending {vector_pending}, failed {vector_failed}, skipped {vector_skipped}\n"
            "🧵 <b>Vector backfill:</b> {vector_backfill}\n"
            "🧾 <b>Записанные ответы agent-а:</b> {agent_replies}"
        ),
        "ask_usage": (
            "💬 Использование: <code>/ask вопрос</code> или ответьте на сообщение/медиа командой " "<code>/ask</code>."
        ),
        "ask_memory_off": (
            "🧠 Память группы выключена. Попросите владельца группы сначала выполнить <code>/memory on</code>."
        ),
        "ask_agent_unavailable": "😵 AI agent сейчас недоступен.",
        "ask_multimodal_unavailable": "😵 Понимание медиа сейчас недоступно.",
        "ask_media_unsupported": (
            "Я могу читать изображения, voice/audio, PDF и text/code/log файлы через /ask, "
            "но этот тип медиа пока не поддерживается."
        ),
        "ask_media_too_large": "Я не смог прочитать это медиа: файл слишком большой.",
        "ask_media_unavailable": (
            "Я не смог прочитать это медиа. Оно может быть недоступно, просрочено или не скачиваться."
        ),
        "ask_daily_quota_exhausted": "⚠️ Дневная квота AI на сегодня исчерпана.",
        "forget_group_done": "🧹 Удалено элементов памяти для этой группы: {deleted}.\n{vector_note}",
        "forget_me_no_user": "❌ Я не смог определить ваш Telegram user id.",
        "forget_me_done": "🧹 Удалено элементов памяти, связанных с вами в этой группе: {deleted}.\n{vector_note}",
        "memory_about_me_empty": "🧠 У меня пока нет сохраненного профиля для вас в этой группе.",
        "memory_about_me_message": (
            "🧠 <b>Я знаю это из ваших собственных сообщений:</b>\n"
            "- стиль языка: {language_style}\n"
            "- частые темы: {common_topics}\n"
            "- заявленные предпочтения: {preferences}\n"
            "- заявленный background: {background}\n"
            "- границы: {boundaries}\n\n"
            "Используйте <code>/memory forget me</code>, чтобы удалить вашу user memory."
        ),
        "forget_this_usage": ("Ответьте на ответ бота или source-сообщение командой <code>/memory forget this</code>."),
        "forget_this_not_allowed": (
            "❌ Вы можете удалять только память, связанную с вашими сообщениями. "
            "Владелец группы или bot owner может удалять group memory."
        ),
        "forget_this_no_sources": "🧠 У этого ответа бота нет записанных источников памяти, которые можно удалить.",
        "forget_this_nothing_deleted": "🧠 Я не нашел сохраненную память для этого сообщения.",
        "forget_this_done": "🧹 Удалено связанных элементов памяти: {deleted}.\n{vector_note}",
        "wrong_memory_usage": (
            "Ответьте на ответ бота командой <code>/agent wrong</code> или <code>/memory wrong</code>."
        ),
        "wrong_memory_no_sources": "🧠 У этого ответа нет сохраненных источников памяти, которые можно отметить.",
        "wrong_memory_done": (
            "🧠 Источники памяти отмечены как ошибочные: {marked}. В будущих ответах они будут ранжироваться ниже."
        ),
        "vector_configured_yes": "да",
        "vector_configured_no": "нет",
        "vector_backfill_none": "-",
        "vector_backfill_queued": "поставлен в очередь",
        "vector_backfill_queued_next_page": "поставлен в очередь; есть следующие страницы",
        "vector_backfill_queued_with_failures": "поставлен в очередь с ошибками",
        "vector_backfill_progress": (
            "обработано {processed_total}, поставлено в очередь {enqueued_total}, ошибок {failures_total}"
        ),
        "vector_cleanup_deleted": "Запрошено удаление indexed vector-памяти: {deleted}.",
        "vector_cleanup_skipped": "Очистка vector-памяти не настроена.",
        "vector_cleanup_delayed": "Очистка vector-памяти не полностью подтверждена; сохраненная память удалена.",
        "why_reply_missing": "🤷 У меня нет записанной причины для этого ответа.",
        "why_reply_message": (
            "🧾 <b>Почему я ответил</b>\n"
            "Причина: {reason}\n"
            "Триггер: {trigger}\n"
            "Уверенность: {confidence}\n"
            "{sources}"
        ),
        "why_sources_none": "Источники памяти: не записаны",
        "why_sources_header": "Источники памяти:",
        "why_sources_item": "- {label}: {value}",
        "why_source_yes": "да",
        "why_source_requester_profile": "профиль запросившего",
        "why_source_target_profile": "профиль целевого пользователя",
        "why_source_semantic": "семантическая память",
        "why_source_lexical": "лексическая память",
        "why_source_long_term": "долгосрочная память группы",
        "why_source_recent": "недавний контекст",
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
