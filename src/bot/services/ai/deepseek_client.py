"""DeepSeek API client for tech-term explanations (OpenAI-compatible chat/completions)."""

import json
from typing import Any

import urllib3
from core.config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from core.logger import LoggerAdapter, get_logger
from services.ai.wtf_prompts import WTFPromptStyle, build_wtf_openai_chat_payload

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=15))


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
        logger.info("DeepSeekClient initialized", extra={"model": self.model})

    def explain_term(self, term: str, lang: str = "kk", style: WTFPromptStyle = "angry") -> str:
        """Ask the LLM to explain a tech term in the given language."""
        payload: dict[str, Any] = build_wtf_openai_chat_payload(self.model, term, lang, style=style)

        url = f"{self.api_base}/chat/completions"
        logger.info(
            "DeepSeek explain request started",
            extra={"model": self.model, "lang": lang, "style": style, "term_chars": len(term)},
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

        body = resp.data.decode("utf-8")

        if resp.status == 429:
            logger.warning("DeepSeek API rate limit hit", extra={"status": resp.status, "body": body[:200]})
            raise DeepSeekRateLimitError(resp.status, body)

        if resp.status >= 400:
            logger.error("DeepSeek API error", extra={"status": resp.status, "body": body[:200]})
            raise DeepSeekAPIError(resp.status, body)

        data = json.loads(body)
        text = data["choices"][0]["message"]["content"].strip()
        logger.info("DeepSeek explain response parsed", extra={"model": self.model, "response_chars": len(text)})
        return text
