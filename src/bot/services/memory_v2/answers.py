"""One leased answer owner; durable receipts contain references, never answer prose."""

import hashlib
import inspect
from dataclasses import dataclass

from .answer_rendering import pagination_text, render_facts, render_trends, unknown_text
from .leases import AnswerLeaseService, fact_references
from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, chat_key, positive_id


@dataclass(frozen=True)
class AnswerOutcome:
    state: str
    message_ids: tuple[int, ...] = ()
    has_more: bool = False


class MemoryAnswerService:
    def __init__(self, repo, *, authorize, sender, selector_factory, subject_usernames=lambda *_: {}):
        self.repo = repo
        self.leases = AnswerLeaseService(repo)
        self.authorize = authorize
        self.sender = sender
        self.selector_factory = selector_factory
        self.subject_usernames = subject_usernames

    async def _authorized(self, chat_id, actor):
        result = self.authorize(chat_id, actor)
        return (await result if inspect.isawaitable(result) else result) is True

    async def answer(
        self,
        chat_id,
        actor_user_id,
        subject_ids,
        *,
        request_id,
        question,
        lang,
        reply_to_message_id,
        about=False,
        page=0,
        include_trends=False,
        request_validator=lambda: None,
    ):
        actor = positive_id(actor_user_id)
        positive_id(reply_to_message_id)
        if int(chat_id) >= 0 or not await self._authorized(chat_id, actor):
            raise MemoryUnavailable("Answer requires current group membership")
        if type(page) is not int or not 0 <= page <= 7 or (not about and page):
            raise MemoryInputError("Unsupported profile page")
        # Duplicate delivery must not turn into a second plain or memory answer.
        control = self.repo._active_control(chat_id)
        readable = []
        for name in subject_ids:
            name = "GROUP" if name == "GROUP" else positive_id(name)
            subject = self.repo.get_subject(chat_id, name)
            if (
                subject
                and subject.get("epoch") == control["epoch"]
                and subject.get("state") == "ACTIVE"
                and not subject.get("optout")
            ):
                readable.append(name)
        subject_ids = tuple(dict.fromkeys(readable))
        request_validator()
        self.leases.retry_unsent(chat_id, request_id)
        lease = self.leases.acquire(chat_id, subject_ids, request_id=request_id, actor_user_id=actor)
        try:
            request_validator()
            facts = self.leases.snapshot(lease)
            trend_owner, trend_view = None, None
            if include_trends:
                from .trend_service import TrendService

                if not about:
                    raise MemoryInputError("Topic samples are deterministic group-profile output")
                trend_owner = TrendService(self.repo)
                trend_view = trend_owner.read(chat_id, max_sources=10)
            has_more = False
            if about:
                page_size = 8 if include_trends else 16
                selected = facts[page * page_size : (page + 1) * page_size]
                has_more = len(facts) > (page + 1) * page_size
                mode = "facts" if selected else "unknown"
            else:

                async def validate():
                    request_validator()
                    self.leases.snapshot(lease)

                selector = self.selector_factory(validate)
                mode, indices = await selector.select(
                    question,
                    facts,
                    subject_ids,
                    requester_user_id=actor,
                    subject_usernames=self.subject_usernames(chat_id, subject_ids),
                )
                selected = [facts[i] for i in indices]
            if mode == "general":
                return AnswerOutcome("GENERAL")
            refs = fact_references(
                [{"fact_id": fact["fact_id"], "fact_version": int(fact["fact_version"])} for fact in selected]
            )
            lease = self.leases.bind(lease, refs, extra_source_refs=trend_view.source_refs if trend_view else ())
            texts = (
                render_facts(chat_id, selected, lang=lang, include_tokens=about, now=self.repo.now())
                if selected
                else (() if trend_view else (unknown_text(lang),))
            )
            if trend_view:
                texts += render_trends(trend_view, lang)
            if about and has_more:
                texts += (pagination_text(lang, page, group=include_trends),)
            row = None
            sent = []
            for index, text in enumerate(texts):
                request_validator()
                if trend_view:
                    trend_owner.validate_snapshot(trend_view)
                self.leases.validate(lease, refs)
                if not await self._authorized(chat_id, actor):
                    raise MemoryUnavailable("Requester left the group before answer delivery")
                self.leases.validate(lease, refs)
                request_validator()
                if row is None:
                    row = self._prepare(lease, actor, request_id, len(texts))
                row = self._step(row, index, "SENDING")
                self.leases.validate(lease, refs)
                request_validator()
                # The injected sender must perform one cancellable <=20s HTTP attempt,
                # return the actual expected-chat message ID, and never retry blindly.
                try:
                    message_id = await self.sender(chat_id, text, reply_to_message_id=reply_to_message_id)
                    if type(message_id) is not int or message_id <= 0:
                        raise MemoryUnavailable("Answer delivery is unconfirmed")
                except Exception:
                    self._step(row, index, "UNKNOWN")
                    return AnswerOutcome("UNKNOWN", tuple(sent), has_more)
                row = self._sent(row, index, message_id)
                sent.append(message_id)
            return AnswerOutcome("SENT", tuple(sent), has_more)
        finally:
            self.leases.release(lease)

    def _prepare(self, lease, actor, request_id, chunks):
        bound, control, subjects = self.leases._live(lease)
        row = {
            "pk": chat_key(lease.chat_id),
            "sk": "ANSWER_REQUEST#" + hashlib.sha256(request_id.encode()).hexdigest(),
            "kind": "ANSWER_REQUEST",
            "revision": 1,
            "epoch": lease.epoch,
            "actor_user_id": actor,
            "subject_ids": list(lease.subject_ids),
            "fact_refs": bound["fact_refs"],
            "source_refs": bound["source_refs"],
            "evidence_authors": bound["evidence_authors"],
            "lease_id": lease.lease_id,
            "steps": [{"state": "READY"} for _ in range(chunks)],
            "state": "READY",
            "created_at": self.repo.now(),
            "ttl": self.repo.now() + 30 * 86400,
        }
        self.repo._transaction(
            [*self.leases._checks([control, *subjects]), self.leases._lease_check(bound), self.repo._put_cas(row, {})]
        )
        return row

    def _step(self, row, index, state):
        old_state = row["steps"][index]["state"]
        if (state == "SENDING" and old_state != "READY") or (state == "UNKNOWN" and old_state != "SENDING"):
            raise MemoryConflict("Answer delivery step changed")
        steps = [dict(step) for step in row["steps"]]
        steps[index] = {"state": state}
        updated = {**row, "revision": int(row["revision"]) + 1, "steps": steps, "state": state}
        self.repo._transaction([self.repo._put_cas(updated, row)])
        return updated

    def _sent(self, row, index, message_id):
        steps = [dict(step) for step in row["steps"]]
        steps[index] = {"state": "SENT", "message_id": message_id}
        updated = {
            **row,
            "revision": int(row["revision"]) + 1,
            "steps": steps,
            "state": "SENT" if all(step["state"] == "SENT" for step in steps) else "PARTIAL",
        }
        receipt = {
            key: row[key]
            for key in (
                "pk",
                "epoch",
                "actor_user_id",
                "subject_ids",
                "fact_refs",
                "source_refs",
                "evidence_authors",
                "ttl",
            )
        }
        receipt.update(
            sk=f"ANSWER_REPLY#{message_id}",
            kind="ANSWER_REPLY",
            revision=1,
            request_key=row["sk"],
            message_id=message_id,
        )
        self.repo._transaction([self.repo._put_cas(updated, row), self.repo._put_cas(receipt, {})])
        return updated

    def reply_subjects(self, chat_id, message_id):
        """Only identity hints; callers must acquire a new lease and read current facts.

        Missing/expired/deleted receipts return no context. Never substitute the
        text quoted in Telegram or a legacy AGENT_REPLY body.
        """
        key = "ANSWER_REPLY#" + positive_id(message_id)
        row = self.repo._read(chat_id, key)
        control = self.repo.get_control(chat_id)
        if (
            not row
            or row.get("kind") != "ANSWER_REPLY"
            or int(row.get("ttl", 0)) <= self.repo.now()
            or row.get("epoch") != control.get("epoch")
            or control.get("state") != "ACTIVE"
        ):
            return ()
        return tuple(row["subject_ids"])
