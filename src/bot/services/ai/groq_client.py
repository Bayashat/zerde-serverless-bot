"""Groq API client for tech-term explanations (OpenAI-compatible chat/completions)."""

import json
from typing import Any

import urllib3
from core.config import GROQ_API_BASE, GROQ_API_KEY, GROQ_MODEL
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=15))

SYSTEM_PROMPT = (
    "You are a veteran programmer with 20 years of experience — cynical but kind-hearted. "
    "You explain technical terms in Kazakh language — briefly, with humor and programmer memes. "
    "Format: 2-4 sentences, max 300 characters. You may use 1-2 emojis. "
    "No Markdown, no lists, no headings. Just plain chat text. "
    "CRITICAL: You MUST reply entirely in Kazakh (Cyrillic script).\n\n"
    "Example Output Style (Reference only, not a strict template):\n"
    "Term: Microservices\n"
    "Микросервистер — бұл монолитті бағдарламаңызды кішкентай 50 бөлікке бөліп тастау. "
    "Енді бір қатені табу үшін сен бір жерді емес, бүкіл желіні шарлап шығасың. "
    "Есесіне түйіндемеңде 'Microservices architecture' деп мақтанып жаза аласың. 🕸️"
)


class GroqAPIError(Exception):
    """Raised when the Groq API returns an error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(status, body)


class GroqClient:
    """Thin HTTP wrapper around the Groq chat/completions endpoint."""

    def __init__(self) -> None:
        self.api_base = GROQ_API_BASE
        self.model = GROQ_MODEL
        self.api_key = GROQ_API_KEY

    def explain_term(self, term: str) -> str:
        """Ask the LLM to explain a tech term in humorous Kazakh."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
        )

        if resp.status >= 400:
            body = resp.data.decode("utf-8")
            logger.error("Groq API error", extra={"status": resp.status, "body": body})
            raise GroqAPIError(resp.status, body)

        data = json.loads(resp.data.decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
