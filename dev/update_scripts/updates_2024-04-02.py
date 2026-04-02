import os

import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

message = (
    "🚀 <b>Zerde Bot Жаңартулары (Updates):</b>\n",
    "📢 1. Енді чатқа жаңа мүшелер қосылған кезде немесе таймаут уақыты аяқталғаннан кейін <i>«User joined the Group»</i> хабарламалары сақталмайды.\n",  # noqa: E501
    "🚫 2. Қолданушы бан алған соң, оның банға байланысты хабарламасы да автоматты түрде өшіріледі.\n",
    "⚖️ 3. Топ сыртындағы мүшелер енді банға дауыс бере алмайды.\n",
    "🤖 <b>Zerde Bot</b>  -  сіздің қауыпсіздігіңіз үшін",
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
