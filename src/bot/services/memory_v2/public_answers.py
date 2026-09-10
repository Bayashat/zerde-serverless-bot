"""Explicit text questions read V2 synchronously; no queued preassembled memory."""

import asyncio

from .answer_selector import AnswerSelectionUnavailable
from .answers import MemoryAnswerService
from .explicit_request_gate import capture, validate
from .identity import IdentityDirectory, select_subjects, username
from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, positive_id
from .safety import require_public_content


class MemoryPublicRetryRequiredError(RuntimeError):
    """A source/command state operation needs authenticated update redelivery."""


class MemoryPublicAnswers:
    def __init__(self, repo, api, *, selector_factory, bot_username):
        self.repo, self.api = repo, api
        self.selector_factory, self.bot_username = selector_factory, bot_username
        self.members = {}
        self.service = MemoryAnswerService(
            repo,
            authorize=api.authorize,
            sender=api.send,
            selector_factory=selector_factory,
            subject_usernames=self._usernames,
        )

    def _usernames(self, chat_id, ids):
        result = {}
        for user_id in ids:
            value = ((self.members.get(str(user_id)) or {}).get("user") or {}).get("username")
            try:
                result[str(user_id)] = username(value)
            except MemoryInputError:
                pass
        # A duplicated current alias is deliberately not an identity hint.
        return {key: value for key, value in result.items() if list(result.values()).count(value) == 1}

    async def _members(self, chat_id, user_ids):
        async def one(actor):
            self.members[str(actor)] = await self.api.member(chat_id, actor)

        await asyncio.gather(*(one(actor) for actor in set(user_ids)))

    async def _selection(self, chat_id, message):
        aliases = set()

        # Extract aliases through the same UTF-16/Telegram-entity validator.
        def collect(alias):
            aliases.add(alias)
            raise MemoryUnavailable("Alias awaits live verification")

        initial = select_subjects(
            message,
            bot_username=self.bot_username,
            resolve_alias=collect,
            reply_subjects=lambda mid: self.service.reply_subjects(chat_id, mid),
        )
        candidates = set(initial.subject_ids)
        for alias in aliases:
            for index, row in enumerate(self.repo._list(chat_id, f"ALIAS#{alias}#USER#")):
                if index >= 64:
                    raise MemoryUnavailable("Alias inventory exceeds bounded lookup")
                if int(row.get("ttl", 0)) > self.repo.now():
                    candidates.add(positive_id(row.get("actor_user_id")))
                if len(candidates) > 8:
                    raise MemoryUnavailable("Alias identity is ambiguous")
        await self._members(chat_id, candidates - {"GROUP"})
        directory = IdentityDirectory(self.repo, get_chat_member=lambda _chat, actor: self.members.get(str(actor), {}))
        selected = select_subjects(
            message,
            bot_username=self.bot_username,
            resolve_alias=lambda alias: directory.resolve(chat_id, alias),
            reply_subjects=lambda mid: self.service.reply_subjects(chat_id, mid),
        )
        return selected

    async def try_answer(self, message, *, question, lang, about=False, group=False, page=0):
        """True consumes this update; False permits plain explicit QA without facts."""
        chat_id = (message.get("chat") or {}).get("id")
        actor = positive_id((message.get("from") or {}).get("id"))
        control = self.repo.get_control(chat_id)
        if control.get("state") != "ACTIVE":
            return False
        original = message.get("date")
        if (
            type(original) is not int
            or original < int(control["learning_started_at"])
            or original < self.repo.now() - 86400
            or original > self.repo.now() + 300
            or message.get("edit_date")
        ):
            return True
        require_public_content(question, max_length=4000)
        try:
            gate = capture(self.repo, chat_id, actor, message["message_id"], requested_at=original)
            if about:
                subjects, unresolved = ("GROUP",) if group else (actor,), False
            else:
                selected = await self._selection(chat_id, message)
                subjects = tuple(dict.fromkeys((*selected.subject_ids, "GROUP")))
                if len(subjects) > 8:
                    raise MemoryUnavailable("Too many explicitly selected people")
                unresolved = bool(selected.unresolved_aliases)
            # Unresolved named people must not silently become requester facts.
            if unresolved:
                subjects = ()
            result = await self.service.answer(
                chat_id,
                actor,
                subjects,
                request_id=f"tg:{chat_id}:{positive_id(message.get('message_id'))}",
                question=question,
                lang=lang,
                reply_to_message_id=message["message_id"],
                about=about or unresolved,
                page=page,
                include_trends=about and group,
                request_validator=lambda: validate(self.repo, chat_id, actor, message["message_id"], gate),
            )
            return result.state != "GENERAL"
        except AnswerSelectionUnavailable:
            return False  # No fact text reaches the plain provider or queue.
        except (MemoryConflict, MemoryUnavailable):
            # A duplicate or changed source must never trigger a second/plain answer.
            return True


def try_memory_answer(message, *, question, lang, about=False, group=False, page=0):
    from core.config import AGENT_BOT_USERNAME, get_bot_token, get_gemini_api_key, is_configured_group_chat

    from .answer_selector import GeminiAnswerProvider, MemoryAnswerSelector
    from .runtime import get_memory_budget, get_memory_v2_repo
    from .telegram_api import MemoryTelegramAPI

    repo = get_memory_v2_repo()
    if repo is None:
        return False
    api = MemoryTelegramAPI(get_bot_token(), configured=is_configured_group_chat)

    def selector_factory(validate):
        return MemoryAnswerSelector(
            GeminiAnswerProvider(get_gemini_api_key()), get_memory_budget(), validate_snapshot=validate
        )

    service = MemoryPublicAnswers(repo, api, selector_factory=selector_factory, bot_username=AGENT_BOT_USERNAME)
    try:
        return asyncio.run(
            service.try_answer(message, question=question, lang=lang, about=about, group=group, page=page)
        )
    except MemoryInputError:
        return False  # Sensitive explicit inputs are never sent to a memory provider.
    except Exception:
        raise MemoryPublicRetryRequiredError("Memory answer state requires redelivery") from None
