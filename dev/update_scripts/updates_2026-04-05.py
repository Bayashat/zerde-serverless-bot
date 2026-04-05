import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

message = (
    "🚀 <b>Zerde Bot Жаңартулары (2026-04-05):</b>\n",
    "📢 Топ тазалығын сақтау мақсатында, енді жаңалықтар күніне "
    "<b>тек 1 рет</b>, таңғы сағат <b>10:00</b>-де жіберіледі.\n\n",
    "🤖 <b>Zerde Bot</b>  - Айти чаттардың көмекшісі",
)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": "\n".join(message), "parse_mode": "HTML"}

print("Sending update announcement...")
response = requests.post(url, json=payload)

if response.status_code == 200:
    print("✅ Update announcement sent successfully! Check the group now!")
else:
    print(f"❌ Failed to send update announcement, error code: {response.status_code}")
    print(response.json())
