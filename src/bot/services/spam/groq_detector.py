"""Groq LLaMA spam classifier: Layer-2 async AI classification via SQS worker."""

import json
from dataclasses import dataclass, field

import urllib3
from core.config import GROQ_API_BASE, GROQ_API_KEY, GROQ_MODEL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=8))

_SYSTEM_PROMPT = """\
You are a spam classifier for a Telegram group of IT professionals in Kazakhstan.
Your ONLY task: determine if a message is spam.

SPAM includes:
- Job/gig/income offers with specific payment amounts ($, USD, tenge, ruble),
  especially when redirecting to DM ("в лс", "в личку", "напишите мне")
- VPN service advertisements or recommendations
- Referral contacts (@username or t.me/ links) promoting external bots, channels, or services
- Work-from-home or freelance recruitment targeted at group members
- Selling, renting, or connecting digital services (e.g., ChatGPT Plus, Claude, CapCut, premium accounts)
- Any promotional/commercial content or price lists

NOT_SPAM includes:
- Technical questions, code sharing, IT discussions, IT news or opinions
- Someone asking if anyone knows of job openings (seeking work, not recruiting)
- Mentioning money in context of discussing salaries, product prices, or hypothetical amounts in a technical discussion
- Mentioning "работа/жұмыс" in context of talking about one's own job or company, not recruiting others
- Normal conversation, greetings, jokes, memes
- @username tags that are clearly addressing someone already in the conversation
- Bot commands or feature requests
- Messages in Kazakh (kk), Simplified Chinese (zh) or Russian (ru) about non-commercial topics
- Sharing links (YouTube, GitHub, TikTok, StackOverflow, news articles) without commercial intent
- Bare URLs without any spammy or commercial context

CRITICAL RULE — AVOID FALSE POSITIVES:
A false positive (flagging a legitimate group member as spam) is far worse than missing a spam message.
ONLY output SPAM with confidence >= 0.85 when the commercial or recruitment intent is completely unambiguous.
If you have any doubt, output NOT_SPAM. Human admins will handle edge cases.

Respond ONLY with valid JSON. No explanation. No markdown.
Output format is always:
{"label": "SPAM|NOT_SPAM", "confidence": 0.95, "reason": "reason_code"}

The "reason" field is REQUIRED for every response:
- If label is "SPAM", reason must be exactly one of:
  - "job_offer" - Job/gig/income offers (including DM-redirect gig spam)
  - "vpn_ad" - VPN service advertisements
  - "referral_promo" - Referral/promotional links for external services
  - "selling_services" - Selling/renting digital services or accounts
  - "commercial" - General promotional/commercial content
  - "suspicious_link" - Suspicious or unknown links
- If label is "NOT_SPAM", reason must be exactly "not_spam"

Few-shot examples:

# High confidence SPAM
Message: "Аренда 24/7 и подключение: Claude Pro: 8 часов - 800 💰 ChatGPT Plus: 24 часа - 600 💰 Оплата Kaspi Pay"
{"label": "SPAM", "confidence": 0.99, "reason": "selling_services"}

Message: "OHЛAЙH PAБOTA C DOXOДOM OT 80-230$! @Victoriaa_S7"
{"label": "SPAM", "confidence": 0.99, "reason": "job_offer"}

Message: "Отличный ВПН!!! Телеграм с ним просто летает!! Спасибо!!"
{"label": "SPAM", "confidence": 0.98, "reason": "vpn_ad"}

Message: "За пару движений дам 12500р. срочно!!!"
{"label": "SPAM", "confidence": 0.99, "reason": "job_offer"}

Message: "Приветик. Шабашка на 4 часа. Оплата 7800. Если интересно-пиши в лс"
{"label": "SPAM", "confidence": 0.97, "reason": "job_offer"}

# Medium confidence SPAM
Message: "Ребята, нашел интересный канал про крипту, кому интересно заходите @crypto_news_123"
{"label": "SPAM", "confidence": 0.80, "reason": "referral_promo"}

Message: "Могу помочь с дизайном и фронтендом, пишите в тг @super_designer"
{"label": "SPAM", "confidence": 0.75, "reason": "commercial"}

Message: "http://unknown-domain-earn-money.com/"
{"label": "SPAM", "confidence": 0.70, "reason": "suspicious_link"}

# NOT SPAM — including cases that look superficially suspicious
Message: "кто знает как настроить nginx на ubuntu 24?"
{"label": "NOT_SPAM", "confidence": 0.99, "reason": "not_spam"}

Message: "Ищу работу, есть опыт в Python 3 года, кто знает вакансии?"
{"label": "NOT_SPAM", "confidence": 0.97, "reason": "not_spam"}

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
    reason: str = field(default="unknown")
    error: bool = field(default=False)


class GroqSpamDetector:
    """Thin HTTP wrapper around Groq chat/completions for spam classification."""

    def __init__(self) -> None:
        self.api_base = GROQ_API_BASE
        self.model = GROQ_MODEL
        self.api_key = GROQ_API_KEY
        logger.info("GroqSpamDetector initialized", extra={"model": self.model})

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
        logger.info(
            "Groq spam classification request started",
            extra={"model": self.model, "message_chars": len(text), "max_tokens": payload["max_tokens"]},
        )
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
            extra={
                "model": self.model,
                "label": label,
                "confidence": confidence,
                "reason": reason,
                "response_chars": len(content),
            },
        )
        return SpamCheckResult(label=label, confidence=confidence, reason=reason)
