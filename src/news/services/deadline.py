"""Invocation deadlines and cancellable, size-bounded HTTP for news work."""

import asyncio
import time

from zerde_common.async_http import bounded_async_client


class NewsDeadlineError(RuntimeError):
    pass


class Deadline:
    def __init__(self, seconds: float):
        if seconds <= 0:
            raise NewsDeadlineError("No news execution budget remains")
        self.expires = time.monotonic() + seconds

    def remaining(self, *, reserve: float = 0) -> float:
        value = self.expires - time.monotonic() - reserve
        if value <= 0:
            raise NewsDeadlineError("News execution deadline exhausted")
        return value

    def timeout(self, cap: float):
        return asyncio.timeout(min(cap, self.remaining()))


async def request_bytes(
    method, url, *, deadline, cap, max_bytes, headers=None, payload=None, follow_redirects=False, transport=None
):
    """The timeout includes DNS, connection, headers and the entire streamed body.

    AsyncClient and stream contexts close on cancellation. There is no implicit retry
    and no detached thread that can continue a send after the caller timed out.
    """
    async with deadline.timeout(cap):
        async with bounded_async_client(
            timeout=min(cap, deadline.remaining()),
            follow_redirects=follow_redirects,
            max_redirects=5,
            transport=transport,
        ) as client:
            async with client.stream(method, url, headers=headers, json=payload) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        raise ValueError("News HTTP response exceeded its size limit")
                return response.status_code, bytes(data)
