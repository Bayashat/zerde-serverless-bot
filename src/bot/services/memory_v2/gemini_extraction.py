"""One bounded Gemini REST attempt; no retries, persistence or raw logging."""

import asyncio
import json

import httpx

from .extraction_prompt import MODEL, validate_request

REQUEST_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 1_000_000


class ExtractionProviderError(RuntimeError):
    """No trustworthy structured result; never include source or response text."""


class GeminiExtractionProvider:
    def __init__(self, api_key: str, *, client=None):
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Gemini extraction credentials are unavailable")
        self._api_key = api_key
        self._client = client

    async def generate(self, request: dict) -> dict:
        try:
            validate_request(request)
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                if self._client is not None:
                    return await self._generate(self._client, request)
                async with httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(retries=0),
                    timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=3),
                    follow_redirects=False,
                ) as client:
                    return await self._generate(client, request)
        except Exception:
            # Transport errors and provider bodies can contain source or secrets.
            pass
        # Raise outside the handler so even custom exception-chain loggers cannot
        # recover the discarded transport error or provider body via __context__.
        raise ExtractionProviderError("Gemini extraction attempt did not complete")

    async def _generate(self, client, request: dict) -> dict:
        async with client.stream(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            content=json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._api_key},
            follow_redirects=False,
            timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=3),
        ) as response:
            if response.status_code != 200:
                raise ExtractionProviderError("Gemini extraction returned a non-success status")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ExtractionProviderError("Gemini extraction response exceeded its limit")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ExtractionProviderError("Gemini extraction response was not an object")
            return payload
