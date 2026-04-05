import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

message = [
    "🚀 <b>Zerde Bot жаңартулары (2026-04-06):</b>",
    "🧠 <b> Күнделікті IT Quiz!</b>",
    "Бүгіннен бастап күн сайын сағат <b>13:00</b>-де чатқа IT саласына қатысты сұрақтар (quiz) жіберіліп тұрады.",
    "📚 <b>Тақырыптар:</b>\n"
    "Programming · AI · CI/CD · Cloud · Containers\n"
    "Cybersecurity · Data Structures · Databases · DevOps",
    "📌 <b>Ережелер:</b>\n"
    "• Топтың кез келген мүшесі қатыса алады.\n"
    "• Нәтижелер сақталып, жалпы рейтинг жүргізіледі.\n"
    "• Күн сайын қатарынан дұрыс жауап берсеңіз — үздіксіз streak өседі 🔥",
    "🧪 <b>Тест режимі:</b>\n"
    "Алғашқы аптада бұл мүмкіндік тест режимінде жұмыс істейді, сондықтан барлық сұрақтар <b>«Оңай» (Easy)</b> деңгейінде болады. Бір аптадан кейін сұрақтардың қиындық деңгейі біртіндеп арта бастайды 📈",  # noqa: E501
    "📊 Жеке нәтижеңізді көру үшін: /quizstats",
    "🤖 <b>Zerde Bot</b> — IT қауымдастықтардың көмекшісі",
]

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": "\n\n".join(message), "parse_mode": "HTML"}

print("Sending update announcement...")
response = requests.post(url, json=payload)

if response.status_code == 200:
    print("✅ Update announcement sent successfully! Check the group now!")
else:
    print(f"❌ Failed to send update announcement, error code: {response.status_code}")
    print(response.json())
