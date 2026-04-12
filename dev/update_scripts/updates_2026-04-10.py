import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Fill these before running ─────────────────────────────────────────────────
CHAT_ID = "-1002914248981"  # e.g. "-1001234567890"
LANG = "ru"  # "kk" | "ru" | "zh"
# ─────────────────────────────────────────────────────────────────────────────

MESSAGES = {
    "kk": [
        "🚀 <b>Zerde Bot жаңартулары (2026-04-10):</b>",
        "🛡️ <b>AI-спам анықтау!</b>\n"
        "Енді бот спам хабарламаларды (жарнама, VPN, табыс ұсыныстары) автоматты түрде анықтап, "
        "жіберушіні топтан шығарады.",
        "🧪 <b>Тест режимі (1 апта):</b>\n"
        "Алғашқы аптада бот спам анықтаған сайын топқа қысқаша хабарлама жібереді — "
        "жүйенің дұрыс жұмыс істеп тұрғанын бірге бақылайық.",
        "⚠️ Егер қате кетіп, дұрыс қолданушы шығарылып қалса (өте аз ықтималдылық), "
        "<b>@bayashat</b>-қа хабарласыңыз",  # noqa: E501
        "🤖 <b>Zerde Bot</b> — IT қауымдастықтардың көмекшісі",
    ],
    "ru": [
        "🚀 <b>Обновления Zerde Bot (2026-04-10):</b>",
        "🛡️ <b>AI-детектор спама!</b>\n"
        "Теперь бот автоматически определяет спам-сообщения (реклама, VPN, предложения заработка) "
        "и удаляет нарушителя из группы.",
        "🧪 <b>Тестовый режим (1 неделя):</b>\n"
        "В течение первой недели бот будет отправлять короткое уведомление в чат при каждом "
        "обнаружении спама — следим вместе за работой системы.",
        "⚠️ Если кто-то был удалён по ошибке (вероятность крайне мала), " "пишите: <b>@bayashat</b>",
        "🤖 <b>Zerde Bot</b> — помощник IT-сообществ",
    ],
    "zh": [
        "🚀 <b>Zerde Bot 更新 (2026-04-10)：</b>",
        "🛡️ <b>AI 垃圾信息检测！</b>\n"
        "Bot 现在可以自动识别垃圾消息（广告、VPN推广、赚钱邀请等），并将发送者移出群组。",
        "🧪 <b>测试阶段（第一周）：</b>\n"
        "第一周内，每次检测到垃圾信息时，Bot 会在群内发送简短通知 — 大家一起看看系统运行情况。",
        "⚠️ 如有成员被误踢（概率极低），请联系：<b>@bayashat</b>",
        "🤖 <b>Zerde Bot</b> — IT 社群助手",
    ],
}


def send(chat_id: str, lang: str) -> None:
    if lang not in MESSAGES:
        print(f"❌ Unknown lang '{lang}'. Choose from: {list(MESSAGES.keys())}")
        sys.exit(1)

    text = "\n\n".join(MESSAGES[lang])
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    print(f"Sending update announcement (lang={lang}, chat={chat_id})...")
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print("✅ Announcement sent successfully!")
    else:
        print(f"❌ Failed: HTTP {response.status_code}")
        print(response.json())


if __name__ == "__main__":
    if not CHAT_ID or not LANG:
        print("❌ Please fill in CHAT_ID and LANG at the top of the script.")
        sys.exit(1)

    if not BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is not set in .env")
        sys.exit(1)

    send(CHAT_ID, LANG)
