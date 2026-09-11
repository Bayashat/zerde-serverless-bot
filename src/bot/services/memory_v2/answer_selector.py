"""Budgeted fact selection, with no free-form personal answer channel."""

import asyncio
import json
import uuid

from services.memory_budget import MODEL
from services.repositories.rate_limit import RateLimitRepository

from .answer_prompt import build_answer_request, parse_selection, validate_answer_request
from .models import MemoryInputError, MemoryUnavailable


class AnswerSelectionUnavailable(RuntimeError):
    """No optional answer was authorized/completed; never carry raw provider errors."""


class GeminiAnswerProvider:
    def __init__(self, api_key, *, client=None):
        if not isinstance(api_key, str) or not api_key:
            raise AnswerSelectionUnavailable("Missing answer provider credentials")
        self._key = api_key
        self._client = client

    async def generate(self, request):
        validate_answer_request(request)
        try:
            async with asyncio.timeout(20):
                if self._client is not None:
                    return await self._send(self._client, request)
                from zerde_common.async_http import bounded_async_client

                async with bounded_async_client(timeout=20, connect_timeout=3, max_connections=1) as client:
                    return await self._send(client, request)
        except Exception:
            pass
        raise AnswerSelectionUnavailable("Answer provider did not complete")

    async def _send(self, client, request):
        async with client.stream(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            content=json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self._key},
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise AnswerSelectionUnavailable("Answer request was not successful")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 100000:
                    raise AnswerSelectionUnavailable("Answer response exceeds its bound")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise AnswerSelectionUnavailable("Unsupported answer response")
            return payload


class MemoryAnswerSelector:
    def __init__(
        self, provider, budget, *, validate_snapshot, rate_limit=None, attempt_id_factory=lambda: uuid.uuid4().hex
    ):
        self.provider = provider
        self.budget = budget
        self.validate_snapshot = validate_snapshot
        self.rate_limit = rate_limit if rate_limit is not None else RateLimitRepository()
        self.attempt_id_factory = attempt_id_factory

    async def select(self, question, facts, subject_ids, *, requester_user_id=None, subject_usernames=None):
        request = build_answer_request(
            question, facts, subject_ids, requester_user_id=requester_user_id, subject_usernames=subject_usernames
        )
        for _ in range(2):
            await self.validate_snapshot()
            try:
                self.budget.check_available()
                count, allowed = self.rate_limit.increment_and_check()
                if type(count) is not int or count < 1 or allowed is not True:
                    raise AnswerSelectionUnavailable("Answer provider quota unavailable")
                reservation = self.budget.reserve(self.attempt_id_factory(), purpose="answer", model=MODEL)
                if reservation is None or reservation is False:
                    raise AnswerSelectionUnavailable("No answer budget permit")
            except Exception:
                raise AnswerSelectionUnavailable("Optional memory budget or quota unavailable") from None
            # The full text/model call, including all retries and output, is charged
            # as an answer call, not just the added fact tokens.
            await self.validate_snapshot()
            try:
                payload = await self.provider.generate(request)
            except MemoryUnavailable:
                raise
            except Exception:
                continue  # Unknown billing keeps its entire reservation.
            try:
                self.budget.settle(reservation, payload.get("usageMetadata"))
            except Exception:
                raise AnswerSelectionUnavailable("Answer usage settlement unavailable") from None
            try:
                result = parse_selection(payload, len(facts))
            except (MemoryInputError, TypeError, ValueError, AttributeError):
                continue
            await self.validate_snapshot()
            return result
        raise AnswerSelectionUnavailable("No valid fact selection")
