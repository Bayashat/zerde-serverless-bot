"""Guard plain/media queued answers with the same source/actor send lease owner."""

import asyncio
from contextlib import contextmanager

from .answers import MemoryAnswerService
from .explicit_request_gate import validate
from .models import MemoryInputError, MemoryUnavailable, SourceRef


class ExplicitDelivery:
    def __init__(self, repo, legacy_repo, bot, body, api):
        self.repo, self.legacy_repo, self.bot, self.body, self.api = repo, legacy_repo, bot, body, api
        self.chat = body["chat_id"]
        self.actor = str(body["requester_user_id"])
        self.message = body["reply_to_message_id"]
        self.request_id = f"tg:{self.chat}:{self.message}"
        self.service = MemoryAnswerService(repo, authorize=api.authorize, sender=api.send, selector_factory=None)
        self.lease = None
        self.sent = False
        validate(repo, self.chat, self.actor, self.message, body.get("request_gate"))
        self.media_refs = self._reload_media()

    def _reload_media(self):
        result, albums = [], {}
        cached = self.body.get("media_refs") or ([self.body["media_ref"]] if self.body.get("media_ref") else [])
        if len(cached) > 4:
            raise MemoryInputError("Too many explicit media sources")
        for item in cached:
            if not isinstance(item, dict):
                raise MemoryInputError("Invalid explicit media reference")
            ref = item.get("ephemeral_source_ref")
            if ref is not None:
                album = item.get("media_group_id")
                if album not in albums:
                    albums[album] = self.legacy_repo.get_media_group_refs(self.chat, album)
                current = next(
                    (
                        entry
                        for entry in albums[album]
                        if entry.get("source_message_id") == item.get("source_message_id")
                        and entry.get("ephemeral_source_ref") == ref
                    ),
                    None,
                )
                if current is None:
                    raise MemoryUnavailable("Queued album source was changed or erased")
                result.append(current)
            else:
                # An explicitly attached/replied single file is request input; it is
                # not a saved memory. It never supplies a retained personal fact.
                result.append(item)
        return result

    def start(self):
        self.check()
        if not asyncio.run(self.api.authorize(self.chat, self.actor)):
            raise MemoryUnavailable("Explicit requester is no longer a group member")
        self.service.leases.retry_unsent(self.chat, self.request_id)
        self.lease = self.service.leases.acquire(
            self.chat, [], request_id=self.request_id, actor_user_id=self.actor, plain=True
        )
        refs = [
            SourceRef(**item["ephemeral_source_ref"]) for item in self.media_refs if item.get("ephemeral_source_ref")
        ]
        self.lease = self.service.leases.bind(self.lease, [], extra_source_refs=refs, extra_source_kind="media")

    def check(self):
        validate(self.repo, self.chat, self.actor, self.message, self.body.get("request_gate"))
        if self.lease:
            self.service.leases.validate(self.lease, [])
        # Cached membership is not a durable authorization for source use.
        if self.media_refs != self._reload_media():
            raise MemoryUnavailable("Explicit media source snapshot changed")

    def get_file(self, *args, **kwargs):
        self.check()
        return self.bot.get_file(*args, **kwargs)

    def download_file(self, *args, **kwargs):
        self.check()
        return self.bot.download_file(*args, **kwargs)

    def send_message(self, chat_id, text, *, reply_to_message_id=None, **kwargs):
        if str(chat_id) != str(self.chat) or reply_to_message_id != self.message or kwargs or self.sent:
            raise MemoryInputError("Explicit guarded send changed its destination/options")
        self.check()
        if not asyncio.run(self.api.authorize(self.chat, self.actor)):
            raise MemoryUnavailable("Explicit requester left before delivery")
        self.check()
        row = self.service._prepare(self.lease, self.actor, self.request_id, 1)
        row = self.service._step(row, 0, "SENDING")
        self.check()
        self.sent = True  # An uncertain network call never permits a second send.
        try:
            message_id = asyncio.run(self.api.send(self.chat, text, reply_to_message_id=self.message))
        except Exception:
            if row:
                self.service._step(row, 0, "UNKNOWN")
            raise MemoryUnavailable("Explicit delivery was not confirmed") from None
        if row:
            self.service._sent(row, 0, message_id)
        return {"message_id": message_id, "chat": {"id": int(self.chat)}}

    def close(self):
        if self.lease:
            self.service.leases.release(self.lease)

    def __getattr__(self, name):
        return getattr(self.bot, name)


@contextmanager
def configured_delivery(legacy_repo, bot, body):
    from core.config import get_bot_token, is_configured_group_chat

    from .runtime import get_memory_v2_repo
    from .telegram_api import MemoryTelegramAPI

    repo = get_memory_v2_repo()
    if repo is None:
        yield bot, body
        return
    api = MemoryTelegramAPI(get_bot_token(), configured=is_configured_group_chat)
    guard = ExplicitDelivery(repo, legacy_repo, bot, body, api)
    try:
        guard.start()
        current = {**body, "media_refs": guard.media_refs}
        current.pop("media_ref", None)
        yield guard, current
    finally:
        guard.close()
