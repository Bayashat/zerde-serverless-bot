"""Bounded live authorization reads and one attempt for leased delivery."""

import asyncio
import contextvars
import copy
import json
import logging
import re
import time

import httpx

from .models import MemoryInputError, MemoryUnavailable, chat_key, positive_id

_LOOKUP_DEADLINE = 20
_READ_ATTEMPT_DEADLINE = 8
_READ_RETRY_DELAY = 0.25
_TELEGRAM_HTTP = contextvars.ContextVar("memory_telegram_http", default=False)
logger = logging.getLogger(__name__)


class _TelegramRequestFilter(logging.Filter):
    def filter(self, record):
        return not _TELEGRAM_HTTP.get()


# These are HTTPX/HTTPCore's request/connection trace owners. Suppress only this
# async context: even a successful HTTPX INFO request contains the bot credential.
for _logger_name in (
    "httpx",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
    "httpcore.connection_pool",
):
    logging.getLogger(_logger_name).addFilter(_TelegramRequestFilter())


class _TelegramFailure(Exception):
    def __init__(self, reason, retryable=False):
        self.reason, self.retryable = reason, retryable
        super().__init__(reason, retryable)


class TelegramReadRetryRequired(RuntimeError):
    """A safe read failed; the authenticated request may be retried."""


class MemoryTelegramAPI:
    def __init__(self, token, *, client=None, configured=lambda _: False):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
            raise MemoryInputError("Invalid Telegram credential configuration")
        self._token, self._client, self.configured = token, client, configured

    async def call(self, method, payload):
        if method not in {"getChatMember", "getMe", "sendMessage"}:
            raise MemoryInputError("Unsupported memory Telegram operation")
        readonly = method in {"getChatMember", "getMe"}
        if readonly:
            payload = copy.deepcopy(payload)
        attempts, reason, result = 0, "LOOKUP_DEADLINE", None
        started = time.monotonic()
        token = _TELEGRAM_HTTP.set(True)
        try:
            # The outer deadline includes both attempts, delay, client teardown
            # and streamed body. It never restarts when the first attempt fails.
            async with asyncio.timeout(_LOOKUP_DEADLINE):
                for attempt in range(2 if readonly else 1):
                    attempts += 1
                    retryable = False
                    try:
                        async with asyncio.timeout(_READ_ATTEMPT_DEADLINE if readonly else _LOOKUP_DEADLINE):
                            result = await self._attempt(method, payload)
                        break
                    except _TelegramFailure as exc:
                        reason, retryable = exc.reason, exc.retryable
                    except (httpx.UnsupportedProtocol, httpx.LocalProtocolError):
                        reason = "UNSUPPORTED_TRANSPORT"
                    except (httpx.TransportError, TimeoutError):
                        # The current shared adapter intentionally folds network
                        # and protocol failures into TransportError. One bounded
                        # READ retry is safe; this does not classify their cause.
                        reason, retryable = "TRANSPORT_UNAVAILABLE", True
                    if not readonly or not retryable or attempt == 1:
                        break
                    await asyncio.sleep(_READ_RETRY_DELAY)
        except TimeoutError:
            reason = "LOOKUP_DEADLINE"
        except Exception:
            reason = "INVALID_RESPONSE"
        finally:
            _TELEGRAM_HTTP.reset(token)
        metadata = {
            "telegram_operation": method,
            "attempts": attempts,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        if result is not None:
            if attempts > 1:
                logger.info("Telegram authorization read recovered", extra=metadata)
            return result
        logger.warning("Telegram operation unavailable", extra={**metadata, "reason": reason})
        # Neither the token-bearing URL nor the original exception chain escapes.
        if method != "sendMessage":
            raise TelegramReadRetryRequired("Telegram authorization lookup requires retry")
        raise MemoryUnavailable("Telegram memory operation was not confirmed")

    async def _attempt(self, method, payload):
        if self._client is not None:
            return await self._request(self._client, method, payload)
        from zerde_common.async_http import bounded_async_client

        async with bounded_async_client(timeout=20, connect_timeout=3, max_connections=1) as client:
            return await self._request(client, method, payload)

    async def _request(self, client, method, payload):
        async with client.stream(
            "POST", f"https://api.telegram.org/bot{self._token}/{method}", json=payload, follow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise _TelegramFailure("HTTP_REJECTED", retryable=response.status_code in {500, 502, 503, 504})
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 100000:
                    raise _TelegramFailure("RESPONSE_TOO_LARGE")
            result = json.loads(raw)
            if (
                not isinstance(result, dict)
                or result.get("ok") is not True
                or not isinstance(result.get("result"), dict)
            ):
                raise _TelegramFailure("INVALID_RESPONSE")
            return result["result"]

    async def member(self, chat_id, user_id):
        chat_key(chat_id)
        actor = positive_id(user_id)
        if int(chat_id) >= 0 or self.configured(chat_id) is not True:
            raise MemoryUnavailable("Memory requires a configured source group")
        result = await self.call("getChatMember", {"chat_id": str(chat_id), "user_id": actor})
        if str((result.get("user") or {}).get("id")) != actor:
            raise TelegramReadRetryRequired("Telegram did not confirm the requested identity")
        return result

    async def authorize(self, chat_id, user_id, *, require_admin=False):
        result = await self.member(chat_id, user_id)
        if (result.get("user") or {}).get("is_bot"):
            return False
        if require_admin:
            return result.get("status") in {"administrator", "creator"}
        return result.get("status") in {"member", "administrator", "creator"} or (
            result.get("status") == "restricted" and result.get("is_member") is True
        )

    async def send(self, chat_id, text, *, reply_to_message_id):
        chat_key(chat_id)
        positive_id(reply_to_message_id)
        if not isinstance(text, str) or not text or len(text.encode("utf-16-le")) // 2 > 4096:
            raise MemoryInputError("Memory output exceeds Telegram bounds")
        result = await self.call(
            "sendMessage",
            {
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": "HTML",
                "reply_parameters": {"message_id": int(reply_to_message_id), "allow_sending_without_reply": False},
                "link_preview_options": {"is_disabled": True},
            },
        )
        message_id = result.get("message_id")
        if (
            type(message_id) is not int
            or message_id <= 0
            or str((result.get("chat") or {}).get("id")) != str(chat_id)
            or (result.get("reply_to_message") or {}).get("message_id") != int(reply_to_message_id)
        ):
            raise MemoryUnavailable("Telegram did not confirm the expected answer destination")
        return message_id
