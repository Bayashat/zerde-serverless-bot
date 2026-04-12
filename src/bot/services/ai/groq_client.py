"""Groq API client for tech-term explanations (OpenAI-compatible chat/completions)."""

import json
from typing import Any

import urllib3
from core.config import GROQ_API_BASE, GROQ_API_KEY, GROQ_MODEL
from core.logger import LoggerAdapter, get_logger
from services.ai.wtf_prompts import build_wtf_openai_chat_payload

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=12))


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

    def explain_term(self, term: str, lang: str = "kk") -> str:
        """Ask the LLM to explain a tech term in the given language."""
        payload: dict[str, Any] = build_wtf_openai_chat_payload(self.model, term, lang)

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
            body = resp.data.decode("utf-8")
            logger.error("Groq API error", extra={"status": resp.status, "body": body})
            raise GroqAPIError(resp.status, body)

        data = json.loads(resp.data.decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
