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
            "🧠 <b>Your Quiz Stats</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🏆 Score: <b>{score}</b> points\n"
            "🔥 Streak: <b>{streak}</b> days\n"
            "⭐ Best streak: <b>{best_streak}</b> days\n"
            "📊 Rank: <b>#{rank}</b> / {total_players} players"
        ),
        "quizstats_no_data": "🧠 You haven't answered any quizzes yet. Wait for the next daily quiz!",
        "quizstats_open_private_chat": (
            "📬 I couldn't send you a private message.\n"
            "Please open a chat with me and send /start first, then try /quizstats again."
        ),
        "quiz_not_configured": "⚙️ Quiz is not configured for this bot.",
        "wtf_usage": (
            "🤔 <b>/wtf</b> — cynical IT term explainer\n\n"
            "• <code>/wtf &lt;term&gt;</code> — explain a term\n"
            "• Reply to a message + <code>/wtf</code> — explain that text"
        ),
        "wtf_not_configured": "⚙️ /wtf is currently unavailable (API not configured).",
        "wtf_api_error": "😵 AI is not responding right now, try again later.",
        "wtf_unexpected_error": "😵 Something went wrong, try again later.",
        "wtf_fallback_notice": (
            "⚠️ <b>Today's Gemini daily quota ({total}) is exhausted.</b> "
            "Explanations will use the backup AI until the quota resets (Pacific midnight)."
        ),
        "wtf_fallback_takeover_intro": "🤕 Gemini is taking a coffee break, so the backup AI is jumping in! ⚡",
        "wtf_fallback_rate_limit": "⏳ Backup AI is temporarily rate-limited. Please try again in a minute.",
        "wtf_rpd_footer": "\n\n---\n📊 Gemini RPD: {remaining}/{total}",
        "wtf_gemini_exhausted_no_fallback": (
            "⚠️ Today's Gemini daily quota is exhausted. Configure a fallback AI or try again tomorrow."
        ),
        "genquiz_lambda_not_configured": "❌ Quiz Lambda is not configured.",
        "genquiz_usage": (
            "❌ Usage: /genquiz &lt;topic&gt; [&lt;difficulty&gt; [&lt;lang&gt;]]\n"
            "Order: topic → difficulty → language. "
            "Defaults: difficulty <code>medium</code>, language from this chat (<code>CHAT_LANG_MAP</code>)."
        ),
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
            "✅ <b>Расталғандар:</b> {verified} адам\n"
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
            "🧠 <b>Сіздің Quiz бойынша нәтижеңіз:</b>\n"
            "📍 <b>{chat_title}</b>\n\n"
            "🏆 Жалпы ұпай: <b>{score}</b>\n"
            "🔥 Үздіксіз streak: <b>{streak}</b> күн\n"
            "⭐ Ең ұзақ streak: <b>{best_streak}</b> күн\n"
            "📊 Рейтингтегі орныңыз: <b>#{rank}</b> / {total_players} қатысушы"
        ),
        "quizstats_no_data": "🧠 Сіз әлі ешқандай Quiz сұрағына жауап бермепсіз. Келесі сұрақты жіберіп алмаңыз!",
        "quizstats_open_private_chat": (
            "📬 Сізге жеке хабарлама жібере алмадым.\n" "Алдымен менімен жеке чат ашып, /start пәрменін жіберіңіз"
        ),
        "quiz_not_configured": "⚙️ Quiz бұл бот үшін бапталмаған.",
        "wtf_usage": (
            "🤔 <b>/wtf</b> — техтерминді түсіндіру\n\n"
            "• <code>/wtf &lt;термин&gt;</code> — түсіндіру\n"
            "• Хабарламаға жауап + <code>/wtf</code> — сол мәтінді түсіндіру"
        ),
        "wtf_not_configured": "⚙️ /wtf пәрмені қазір қолжетімсіз (API бапталмаған).",
        "wtf_api_error": "😵 AI қазір жауап бермей тұр, кейінірек қайталап көріңіз.",
        "wtf_unexpected_error": "😵 Белгісіз қате орын алды, кейінірек қайталап көріңіз.",
        "wtf_fallback_notice": (
            "⚠️ <b>Бүгінгі Gemini күнделікті лимиті ({total}) таусылды.</b> "
            "Лимит қайта толғанға дейін түсіндірулер резервтік AI арқылы жүреді (Тынық мұхиты уақыты бойынша түн ортасы)."  # noqa: E501
        ),
        "wtf_fallback_takeover_intro": "<i>🤕 Gemini шай ішуге кетті, сондықтан кезек <b>DeepSeek-те</b>!</i>",
        "wtf_fallback_rate_limit": "⏳ Резервтік AI қазір шектеуге тап болды. Бір минуттан кейін қайталап көріңіз.",
        "wtf_rpd_footer": "\n\n---\n📊 Gemini RPD: {remaining}/{total}",
        "wtf_gemini_exhausted_no_fallback": (
            "⚠️ Бүгінгі Gemini күнделікті лимиті таусылды. Резервтік AI-ды баптаңыз немесе ертең қайталап көріңіз."
        ),
        "genquiz_lambda_not_configured": "❌ Quiz Lambda бапталмаған.",
        "genquiz_usage": (
            "❌ Қолданылуы: /genquiz &lt;тақырып&gt; [&lt;деңгей&gt; [&lt;тіл&gt;]]\n"
            "Реті: тақырып → деңгей → тіл. "
            "Әдепкі: деңгей <code>medium</code>, тіл чаттан (<code>CHAT_LANG_MAP</code>)."
        ),
        "genquiz_invalid_lang": "❌ Тіл қате. Келесілерді таңдаңыз: {langs}",
        "genquiz_invalid_difficulty": "❌ Деңгей қате. Келесілерді таңдаңыз: {difficulties}",
        "genquiz_failed": "❌ Quiz жасау мүмкін болмады: {reason}",
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
            "🛡️ <b>新成员（反垃圾）</b>\n"
            "入群后，请点击 <b>“我是人类”</b> 按钮。\n"
            "⚠️ <i>注意：若 60 秒内未点击，将被自动移出群组。</i>\n\n"
            "📊 <b>管理员功能：</b>\n"
            "• /stats — 查看群组统计和活跃度。\n"
            "• /start — 重启机器人（无响应时）。\n\n"
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
            "🔫 <b>投票封禁：</b> {banned} 人\n\n"
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
            "🏆 积分：<b>{score}</b>\n"
            "🔥 连胜：<b>{streak}</b> 天\n"
            "⭐ 最佳连胜：<b>{best_streak}</b> 天\n"
            "📊 排名：<b>#{rank}</b> / {total_players} 人"
        ),
        "quizstats_no_data": "🧠 你还没有答过 Quiz 题目。请等待下一次每日测验！",
        "quizstats_open_private_chat": (
            "📬 我无法给你发送私信。\n" "请先打开与我的私聊并发送 /start，然后再试一次 /quizstats。"
        ),
        "quiz_not_configured": "⚙️ 本机器人未配置 Quiz 功能。",
        "wtf_usage": (
            "🤔 <b>/wtf</b> — 毒舌程序员风解释术语\n\n"
            "• <code>/wtf &lt;术语&gt;</code> — 解释术语\n"
            "• 回复一条消息 + <code>/wtf</code> — 解释该消息全文"
        ),
        "wtf_not_configured": "⚙️ /wtf 当前不可用（API 未配置）。",
        "wtf_api_error": "😵 AI 当前无响应，请稍后重试。",
        "wtf_unexpected_error": "😵 出现未知错误，请稍后重试。",
        "wtf_fallback_notice": (
            "⚠️ <b>今日 Gemini 配额 ({total}) 已耗尽。</b> " "在配额重置前（太平洋时间午夜），将使用备用 AI。"
        ),
        "wtf_fallback_takeover_intro": "🤕 Gemini 正在休息，备用 AI 顶上啦！⚡",
        "wtf_fallback_rate_limit": "⏳ 备用 AI 触发限流，请 1 分钟后重试。",
        "wtf_rpd_footer": "\n\n---\n📊 Gemini RPD：{remaining}/{total}",
        "wtf_gemini_exhausted_no_fallback": "⚠️ 今日 Gemini 配额已耗尽。请配置备用 AI 或明天再试。",
        "genquiz_lambda_not_configured": "❌ Quiz Lambda 未配置。",
        "genquiz_usage": (
            "❌ 用法：/genquiz &lt;主题&gt; [&lt;难度&gt; [&lt;语言&gt;]]\n"
            "顺序：主题 → 难度 → 语言。\n"
            "默认：难度 <code>medium</code>，语言为本群设置（<code>CHAT_LANG_MAP</code>）。"
        ),
        "genquiz_invalid_lang": "❌ 语言无效。可选：{langs}",
        "genquiz_invalid_difficulty": "❌ 难度无效。可选：{difficulties}",
        "genquiz_failed": "❌ 生成 Quiz 失败：{reason}",
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
            "🛡️ <b>Для новых участников (антиспам):</b>\n"
            "После входа нужно нажать кнопку <b>«Я человек»</b>.\n"
            "⚠️ <i>Важно: если не нажать за 60 секунд, пользователь будет удален автоматически.</i>\n\n"
            "📊 <b>Для администраторов:</b>\n"
            "• /stats — посмотреть статистику и активность группы.\n"
            "• /start — перезапустить бота (если не отвечает).\n\n"
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
            "🔫 <b>Забанено голосованием:</b> {banned}\n\n"
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
            "🏆 Очки: <b>{score}</b>\n"
            "🔥 Серия: <b>{streak}</b> дней\n"
            "⭐ Лучшая серия: <b>{best_streak}</b> дней\n"
            "📊 Ранг: <b>#{rank}</b> / {total_players} игроков"
        ),
        "quizstats_no_data": "🧠 Вы еще не отвечали на Quiz. Дождитесь следующего ежедневного вопроса!",
        "quizstats_open_private_chat": (
            "📬 Я не смог отправить вам личное сообщение.\n"
            "Сначала откройте со мной личный чат и отправьте /start, затем попробуйте /quizstats снова."
        ),
        "quiz_not_configured": "⚙️ Quiz для этого бота не настроен.",
        "wtf_usage": (
            "🤔 <b>/wtf</b> — циничное объяснение IT-термина\n\n"
            "• <code>/wtf &lt;термин&gt;</code> — объяснить\n"
            "• Ответьте на сообщение + <code>/wtf</code> — объяснить текст"
        ),
        "wtf_not_configured": "⚙️ /wtf сейчас недоступен (API не настроен).",
        "wtf_api_error": "😵 AI сейчас не отвечает, попробуйте позже.",
        "wtf_unexpected_error": "😵 Что-то пошло не так, попробуйте позже.",
        "wtf_fallback_notice": (
            "⚠️ <b>Дневная квота Gemini ({total}) исчерпана.</b> "
            "До сброса квоты (полночь по Тихоокеанскому времени) будет использоваться резервный AI."
        ),
        "wtf_fallback_takeover_intro": "🤕 Gemini ушел на перерыв, подключаем резервный AI! ⚡",
        "wtf_fallback_rate_limit": "⏳ Для резервного AI временно сработал лимит. Попробуйте через минуту.",
        "wtf_rpd_footer": "\n---\n📊 Gemini RPD: {remaining}/{total}",
        "wtf_gemini_exhausted_no_fallback": (
            "⚠️ Дневная квота Gemini исчерпана. " "Настройте резервный AI или попробуйте завтра."
        ),
        "genquiz_lambda_not_configured": "❌ Quiz Lambda не настроена.",
        "genquiz_usage": (
            "❌ Использование: /genquiz &lt;тема&gt; [&lt;сложность&gt; [&lt;язык&gt;]]\n"
            "Порядок: тема → сложность → язык. "
            "По умолчанию: сложность <code>medium</code>, язык чата (<code>CHAT_LANG_MAP</code>)."
        ),
        "genquiz_invalid_lang": "❌ Неверный язык. Выберите из: {langs}",
        "genquiz_invalid_difficulty": "❌ Неверная сложность. Выберите из: {difficulties}",
        "genquiz_failed": "❌ Не удалось сгенерировать Quiz: {reason}",
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
