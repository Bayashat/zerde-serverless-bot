"""DeepSeek API client for tech-term explanations (OpenAI-compatible chat/completions)."""

import json
from typing import Any

import urllib3
from core.config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=15))

SYSTEM_PROMPTS: dict[str, str] = {
    "ru": (
        "You are a senior developer with 20 years of experience — brutally honest, cynical, but secretly loves the craft. "  # noqa: E501
        "Your job: explain technical terms in Russian in 2-4 sentences. "
        "Style: roast the term like it ruined your weekend. Be funny, sarcastic, relatable to developers. "
        "Rules: max 300 characters, 1-2 emojis allowed, plain text only, no Markdown, no lists. "
        "CRITICAL: Reply ENTIRELY in Russian. "
        "Example (term: Microservices):\n"
        "Микросервисы — это когда ты берёшь один монолит, разбиваешь его на 50 частей "
        "и получаешь 50 новых проблем вместо одной. "
        "Зато в резюме звучит солидно. 📦"
    ),
    "kk": (
        "You are a senior developer with 20 years of experience — brutally honest, cynical, but secretly loves the craft. "  # noqa: E501
        "Your job: explain technical terms in Kazakh in 2-4 sentences. "
        "Style: roast the term like it ruined your weekend. Be funny, sarcastic, relatable to developers. "
        "Rules: max 300 characters, 1-2 emojis allowed, plain text only, no Markdown, no lists. "
        "CRITICAL: Reply ENTIRELY in Kazakh. "
        "Example (term: Microservices):\n"
        "Микросервистер — бір үлкен проблеманы елу кішігірім проблемаға бөлу өнері. "
        "Бәрі жақсы болады деп ойлайсың, бірақ жүйе түнде өледі де, себебін таппайсың. "
        "Резюмеге жақсы көрінеді дегені рас. 📦"
    ),
    "zh": (
        "You are a senior developer with 20 years of experience — brutally honest, cynical, but secretly loves the craft. "  # noqa: E501
        "Your job: explain technical terms in Chinese (Simplified) in 2-4 sentences. "
        "Style: roast the term like it ruined your weekend. Be funny, sarcastic, relatable to developers. "
        "Rules: max 300 characters, 1-2 emojis allowed, plain text only, no Markdown, no lists. "
        "CRITICAL: Reply ENTIRELY in Simplified Chinese. "
        "Example (term: Microservices):\n"
        "微服务就是把一个大问题拆成五十个小问题，然后假装自己解决了架构难题。 "
        "每个服务都能独立挂掉，而且它们会在最关键的时候轮流表演。 "
        "但简历上写起来确实好看。 📦"
    ),
}

DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPTS["kk"]


class DeepSeekAPIError(Exception):
    """Raised when the DeepSeek API returns an error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(status, body)


class DeepSeekRateLimitError(DeepSeekAPIError):
    """Raised when the DeepSeek API returns HTTP 429 (rate limit exceeded)."""


class DeepSeekClient:
    """Thin HTTP wrapper around the DeepSeek chat/completions endpoint."""

    def __init__(self) -> None:
        self.api_base = DEEPSEEK_API_BASE
        self.model = DEEPSEEK_MODEL
        self.api_key = DEEPSEEK_API_KEY

    def explain_term(self, term: str, lang: str = "kk") -> str:
        """Ask the LLM to explain a tech term in the given language."""
        system_prompt = SYSTEM_PROMPTS.get(lang, DEFAULT_SYSTEM_PROMPT)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Explain the term: {term}"},
            ],
            "max_tokens": 400,
            "temperature": 0.9,
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

        body = resp.data.decode("utf-8")

        if resp.status == 429:
            logger.warning("DeepSeek API rate limit hit", extra={"status": resp.status, "body": body[:200]})
            raise DeepSeekRateLimitError(resp.status, body)

        if resp.status >= 400:
            logger.error("DeepSeek API error", extra={"status": resp.status, "body": body[:200]})
            raise DeepSeekAPIError(resp.status, body)

        data = json.loads(body)
        return data["choices"][0]["message"]["content"].strip()
