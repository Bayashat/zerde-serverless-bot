"""One cancellable Telegram attempt for V2 authorization and leased delivery."""

import asyncio
import json
import re

from .models import MemoryInputError, MemoryUnavailable, chat_key, positive_id


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
        try:
            async with asyncio.timeout(20):
                if self._client is not None:
                    return await self._request(self._client, method, payload)
                from zerde_common.async_http import bounded_async_client

                async with bounded_async_client(timeout=20, connect_timeout=3, max_connections=1) as client:
                    return await self._request(client, method, payload)
        except Exception:
            pass
        # Neither the token-bearing URL nor the original exception chain escapes.
        if method != "sendMessage":
            raise TelegramReadRetryRequired("Telegram authorization lookup requires retry")
        raise MemoryUnavailable("Telegram memory operation was not confirmed")

    async def _request(self, client, method, payload):
        async with client.stream(
            "POST", f"https://api.telegram.org/bot{self._token}/{method}", json=payload, follow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise MemoryUnavailable("Telegram rejected the memory operation")
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 100000:
                    raise MemoryUnavailable("Telegram response exceeds its bound")
            result = json.loads(raw)
            if (
                not isinstance(result, dict)
                or result.get("ok") is not True
                or not isinstance(result.get("result"), dict)
            ):
                raise MemoryUnavailable("Telegram response cannot confirm the operation")
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
