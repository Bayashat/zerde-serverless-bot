"""Groq LLaMA spam classifier: Layer-2 async AI classification via SQS worker."""

import json
from dataclasses import dataclass, field

import urllib3
from core.config import GROQ_API_BASE, GROQ_API_KEY, GROQ_MODEL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=8))

# Replace the prompt body below in one shot when you paste your final copy.
# Few-shot bands: High SPAM / Medium SPAM / NOT SPAM (incl. Kazakh + bot commands).
_SYSTEM_PROMPT = """\
You are a spam classifier for a Telegram group of IT professionals.
Your ONLY task: determine if a message is spam.

SPAM includes:
- Job/income/earning offers with specific amounts ($, USD, tenge, ruble)
- VPN service advertisements or recommendations
- Referral contacts (@username or t.me/ links) promoting external bots, channels, or services
- Work-from-home or freelance recruitment
- Selling, renting, or connecting digital services (e.g., ChatGPT Plus, Claude, CapCut, premium accounts)
- Any promotional/commercial content or price lists

NOT_SPAM includes:
- Technical questions or discussions
- Code sharing
- IT news or opinions
- Normal conversation, greetings, or jokes
- Tagging other users or admins inside the group (e.g., @username)
- Bot commands or feature requests
- Messages in Kazakh (kk) or Russian (ru) languages

Respond ONLY with valid JSON. No explanation. No markdown.
Format: {"label": "SPAM", "confidence": 0.95}

Few-shot examples (vary confidence: High SPAM, Medium SPAM, NOT SPAM):

# High confidence SPAM (obvious scam/ads)
Message: "Аренда 24/7 и подключение: Claude Pro: 8 часов - 800 💰 ChatGPT Plus: 24 часа - 600 💰 Оплата Kaspi Pay"
{"label": "SPAM", "confidence": 0.99}

Message: "OHЛAЙH PAБOTA C DOXOДOM OT 80-230$! @Victoriaa_S7"
{"label": "SPAM", "confidence": 0.99}

Message: "Отличный ВПН!!! Телеграм с ним просто летает!! Спасибо!!"
{"label": "SPAM", "confidence": 0.98}

# Medium confidence SPAM (borderline / suspicious promotions)
Message: "Ребята, нашел интересный канал про крипту, кому интересно заходите @crypto_news_123"
{"label": "SPAM", "confidence": 0.80}

Message: "Могу помочь с дизайном и фронтендом, пишите в тг @super_designer"
{"label": "SPAM", "confidence": 0.75}

# High confidence NOT SPAM (normal IT / group chat)
Message: "кто знает как настроить nginx на ubuntu 24?"
{"label": "NOT_SPAM", "confidence": 0.99}

Message: "Я обычно использую @BotFather для получения токена."
{"label": "NOT_SPAM", "confidence": 0.98}

# High confidence NOT SPAM (group mentions and bot-related Kazakh)
Message: "@bayashat genquiz деп тағы куиз жасаңызшы."
{"label": "NOT_SPAM", "confidence": 0.99}

Message: "@admin удалите это пожалуйста, спам"
{"label": "NOT_SPAM", "confidence": 0.99}\
"""


@dataclass
class SpamCheckResult:
    label: str  # "SPAM" | "NOT_SPAM"
    confidence: float  # 0.0–1.0
    error: bool = field(default=False)


class GroqSpamDetector:
    """Thin HTTP wrapper around Groq chat/completions for spam classification."""

    def __init__(self) -> None:
        self.api_base = GROQ_API_BASE
        self.model = GROQ_MODEL
        self.api_key = GROQ_API_KEY

    def classify(self, text: str) -> SpamCheckResult:
        """Classify text as SPAM or NOT_SPAM. Never raises — returns error result on failure."""
        try:
            return self._call_api(text)
        except Exception as e:
            logger.error("GroqSpamDetector classify failed", extra={"error": e})
            return SpamCheckResult(label="NOT_SPAM", confidence=0.0, error=True)

    def _call_api(self, text: str) -> SpamCheckResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Classify: {text}"},
            ],
            "temperature": 0.0,
            "max_tokens": 64,
        }
        url = f"{self.api_base}/chat/completions"
        resp = _http.request(
            "POST",
            url,
            body=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            retries=False,
        )

        if resp.status >= 400:
            body_text = resp.data.decode("utf-8")
            logger.error("Groq spam API error", extra={"status": resp.status, "body": body_text})
            return SpamCheckResult(label="NOT_SPAM", confidence=0.0, error=True)

        data = json.loads(resp.data.decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        result = json.loads(content)
        label = result["label"]
        confidence = float(result["confidence"])
        logger.info(
            "Groq spam classification result",
            extra={"label": label, "confidence": confidence},
        )
        return SpamCheckResult(label=label, confidence=confidence)
