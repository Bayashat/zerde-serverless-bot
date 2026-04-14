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
- Messages in Kazakh (kk), Simplified Chinese (zh) or Russian (ru) languages
- Sharing general social media, media, or resource links (TikTok, YouTube, GitHub,
  StackOverflow, etc.) without promotional text
- Bare URLs (just a link) without any spammy or commercial context

CRITICAL CONFIDENCE SCORING RULE:
- ONLY give a SPAM confidence >= 0.85 if you are ABSOLUTELY certain
  it is a scam, VPN ad, account selling, or illegal job offer.
- If the message is just an ambiguous link or bare URL (like a TikTok or YouTube video),
  you MUST output NOT_SPAM, or SPAM with a confidence < 0.80 (so human admins can review it).

Respond ONLY with valid JSON. No explanation. No markdown.
Format: {"label": "SPAM", "confidence": 0.95, "reason": "reason_code"}

Reason codes (use ONLY for SPAM label):
- "job_offer" - Job/income/earning offers
- "vpn_ad" - VPN service advertisements
- "referral_promo" - Referral/promotional links for external services
- "selling_services" - Selling/renting digital services or accounts
- "commercial" - General promotional/commercial content
- "suspicious_link" - Suspicious or unknown links

For NOT_SPAM, use "reason": "not_spam"

Few-shot examples (vary confidence: High SPAM, Medium SPAM, NOT SPAM):

# High confidence SPAM (obvious scam/ads)
Message: "Аренда 24/7 и подключение: Claude Pro: 8 часов - 800 💰 ChatGPT Plus: 24 часа - 600 💰 Оплата Kaspi Pay"
{"label": "SPAM", "confidence": 0.99, "reason": "selling_services"}

Message: "OHЛAЙH PAБOTA C DOXOДOM OT 80-230$! @Victoriaa_S7"
{"label": "SPAM", "confidence": 0.99, "reason": "job_offer"}

Message: "Отличный ВПН!!! Телеграм с ним просто летает!! Спасибо!!"
{"label": "SPAM", "confidence": 0.98, "reason": "vpn_ad"}

# Medium confidence SPAM (borderline / suspicious promotions or ambiguous links)
Message: "Ребята, нашел интересный канал про крипту, кому интересно заходите @crypto_news_123"
{"label": "SPAM", "confidence": 0.80, "reason": "referral_promo"}

Message: "Могу помочь с дизайном и фронтендом, пишите в тг @super_designer"
{"label": "SPAM", "confidence": 0.75, "reason": "commercial"}

Message: "http://unknown-domain-earn-money.com/"
{"label": "SPAM", "confidence": 0.70, "reason": "suspicious_link"}

# High confidence NOT SPAM (normal IT / group chat / general links)
Message: "кто знает как настроить nginx на ubuntu 24?"
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}

Message: "Смотрите какая жиза 🤣 https://vm.tiktok.com/ZMxxxxxx/"
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}

Message: "https://youtu.be/dQw4w9WgXcQ"
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}

Message: "https://github.com/tiangolo/fastapi"
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}

Message: "@bayashat genquiz деп тағы куиз жасаңызшы."
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}
"""


@dataclass
class SpamCheckResult:
    label: str  # "SPAM" | "NOT_SPAM"
    confidence: float  # 0.0–1.0
    reason: str = field(default="unknown")  # reason code for spam type
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
        reason = result.get("reason", "unknown")
        logger.info(
            "Groq spam classification result",
            extra={"label": label, "confidence": confidence, "reason": reason},
        )
        return SpamCheckResult(label=label, confidence=confidence, reason=reason)
