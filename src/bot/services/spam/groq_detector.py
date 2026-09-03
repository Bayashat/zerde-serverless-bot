"""Groq spam classifier: Layer-2 async AI classification via SQS worker."""

import json
from dataclasses import dataclass, field

import urllib3
from core.config import GROQ_API_BASE, GROQ_SPAM_MODEL, get_groq_api_key
from core.logger import LoggerAdapter, get_logger
from urllib3.exceptions import HTTPError
from zerde_common.ai_errors import (
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.groq_chat import apply_groq_chat_options

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=8))

_SYSTEM_PROMPT = """\
You are a spam classifier for a Telegram group of IT professionals in Kazakhstan.
Your ONLY task: determine if a message is spam.
You may receive a structured context block with CURRENT_MESSAGE, REPLY_TO_MESSAGE,
QUOTE_CONTEXT, EXTERNAL_REPLY_CONTEXT, RECENT_GROUP_MESSAGES, and RULE_SIGNAL.
Classify ONLY the CURRENT_MESSAGE. Use context only to disambiguate what the current
sender meant. Do not classify previous/replied/quoted messages by themselves.

SPAM includes:
- Job/gig/income offers with specific payment amounts ($, USD, tenge, ruble),
  especially when redirecting to DM ("в лс", "в личку", "напишите мне")
- VPN service advertisements or recommendations
- Referral contacts (@username or t.me/ links) promoting external bots, channels, or services
- Work-from-home or freelance recruitment targeted at group members
- Selling, renting, or connecting digital services (e.g., ChatGPT Plus, Claude, CapCut, premium accounts)
- Any promotional/commercial content or price lists
- Crypto/investment "signals", guaranteed profit, pump groups, trading referrals
- Phishing, credential theft, malware, suspicious giveaways, fake support/admin impersonation
- Account sales, SIM/number sales, marketplace spam
- Adult, gambling, casino or betting promotions

NOT_SPAM includes:
- Technical questions, code sharing, IT discussions, IT news or opinions
- Someone asking if anyone knows of job openings (seeking work, not recruiting)
- Mentioning money in context of discussing salaries, product prices, or hypothetical amounts in a technical discussion
- Group chat price discussions, jokes, ordinary consumer prices, medical/pharmacy prices, or splitting bills
- Mentioning "работа/жұмыс" in context of talking about one's own job or company, not recruiting others
- Tagging, blocking, banning, or moderation jokes/discussions without an external promotion
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
  - "dm_redirect_scam" - DM/private-message redirect scam, especially with money/job hooks
  - "vpn_ad" - VPN service advertisements
  - "referral_promo" - Referral/promotional links for external services
  - "selling_services" - Selling/renting digital services or accounts
  - "account_sale" - Selling accounts, phone numbers, SIMs, or access
  - "crypto_investment" - Crypto/trading/investment profit promotions
  - "phishing" - Credential theft, fake support/admin, malware, suspicious giveaways
  - "adult_gambling" - Adult, casino, betting, gambling promotions
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
{"label": "SPAM", "confidence": 0.97, "reason": "dm_redirect_scam"}

Message: "Инсайды по крипте, x5 за неделю, вход в закрытый канал @profit_signal"
{"label": "SPAM", "confidence": 0.96, "reason": "crypto_investment"}

Message: "Подтвердите аккаунт Telegram, иначе блокировка: http://tg-login-security.example"
{"label": "SPAM", "confidence": 0.98, "reason": "phishing"}

Message: "Продам аккаунты ChatGPT Plus / Claude, гарантия, оплата Kaspi"
{"label": "SPAM", "confidence": 0.96, "reason": "account_sale"}

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

Message: "Смекта 2000тг деп куткарам."
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
        self.model = GROQ_SPAM_MODEL
        api_key = get_groq_api_key()
        if not api_key:
            raise ValueError("GROQ_API_KEY must be set to initialize GroqSpamDetector")
        self.api_key = api_key
        logger.info("GroqSpamDetector initialized", extra={"model": self.model})

    def classify(self, text: str) -> SpamCheckResult:
        """Classify text as SPAM or NOT_SPAM, raising on provider failure."""
        try:
            return self._call_api(text)
        except Exception as e:
            logger.error("GroqSpamDetector classify failed", extra={"error": e})
            if isinstance(e, ZerdeProviderError):
                raise
            raise ProviderResponseError(f"Groq spam response invalid: {e}") from e

    def _call_api(self, text: str) -> SpamCheckResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Classify this structured spam review context:\n{text}"},
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }
        apply_groq_chat_options(payload, model=self.model, max_output_tokens=128)
        url = f"{self.api_base}/chat/completions"
        logger.info(
            "Groq spam classification request started",
            extra={
                "model": self.model,
                "message_chars": len(text),
                "max_completion_tokens": payload["max_completion_tokens"],
            },
        )
        try:
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
        except (HTTPError, OSError) as exc:
            raise ProviderTransportError(f"Groq spam transport error: {exc}") from exc

        if resp.status >= 400:
            body_text = resp.data.decode("utf-8", errors="replace")
            logger.error("Groq spam API error", extra={"status": resp.status, "body": body_text[:500]})
            raise map_http_status_to_provider_error(
                resp.status,
                f"Groq spam API {resp.status}: {body_text[:200]}",
            )

        try:
            data = json.loads(resp.data.decode("utf-8"))
            raw_content = data["choices"][0]["message"]["content"]
        except json.JSONDecodeError as exc:
            raise ProviderResponseError(f"Groq spam response was not valid JSON: {exc}") from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(f"Groq spam response schema invalid: {exc}") from exc
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise ProviderResponseError("Groq returned empty spam classification content")

        content = raw_content.strip()
        try:
            result = json.loads(content)
            if not isinstance(result, dict):
                raise TypeError("classification JSON was not an object")
            label = result["label"]
            if label not in {"SPAM", "NOT_SPAM"}:
                raise ValueError("label must be SPAM or NOT_SPAM")
            confidence = float(result["confidence"])
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
            reason = str(result["reason"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ProviderResponseError(f"Groq returned invalid spam classification JSON: {exc}") from exc
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
