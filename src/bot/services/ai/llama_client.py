"""Meta Llama API client for tech-term explanations (OpenAI-compatible chat/completions)."""

import json
from typing import Any

import urllib3
from core.config import LLAMA_API_BASE, LLAMA_API_KEY, LLAMA_MODEL
from core.logger import LoggerAdapter, get_logger
from services.ai.wtf_prompts import build_wtf_openai_chat_payload

logger = LoggerAdapter(get_logger(__name__), {})

_http = urllib3.PoolManager(maxsize=2, timeout=urllib3.Timeout(total=15))


class LlamaAPIError(Exception):
    """Raised when the Llama API returns an error."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(status, body)


class LlamaRateLimitError(LlamaAPIError):
    """Raised when the Llama API returns HTTP 429 (rate limit exceeded)."""


class LlamaClient:
    """Thin HTTP wrapper around the Meta Llama chat/completions endpoint."""

    def __init__(self) -> None:
        self.api_base = LLAMA_API_BASE
        self.model = LLAMA_MODEL
        self.api_key = LLAMA_API_KEY

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

        body = resp.data.decode("utf-8")

        if resp.status == 429:
            logger.warning("Llama API rate limit hit", extra={"status": resp.status, "body": body[:200]})
            raise LlamaRateLimitError(resp.status, body)

        if resp.status >= 400:
            logger.error("Llama API error", extra={"status": resp.status, "body": body[:200]})
            raise LlamaAPIError(resp.status, body)

        data = json.loads(body)
        return data["choices"][0]["message"]["content"].strip()
