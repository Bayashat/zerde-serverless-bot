"""Authenticated command boundary; Telegram parsing and sending belong to the app."""

from .leases import fact_references
from .models import (
    GROUP_FIELDS,
    MULTI_FIELDS,
    AdminConfirmation,
    EvidenceSpan,
    FactChange,
    MemoryInputError,
    MemoryUnavailable,
    SelfConfirmation,
    SourceEvent,
    chat_key,
    positive_id,
)
from .writer import FactWriter


class MemoryCommandService:
    def __init__(self, repo, lifecycle, *, authorize):
        self.repo = repo
        self.lifecycle = lifecycle
        self.authorize = authorize
        self.writer = FactWriter(repo)

    def _authorize(self, chat_id, actor_user_id, *, admin=False):
        chat_key(chat_id)
        actor = positive_id(actor_user_id)
        if int(chat_id) >= 0 or self.authorize(chat_id, actor, require_admin=admin) is not True:
            raise MemoryUnavailable("Memory command requires current source-group authorization")
        return actor

    def about_subject(self, chat_id, actor_user_id, *, group=False):
        """Return authorized subject selection for the sole leased answer renderer."""
        actor = self._authorize(chat_id, actor_user_id)
        return ["GROUP" if group else actor]

    def _target(self, chat_id, actor_user_id, fact_ref):
        refs = fact_references([fact_ref])
        actor = self._authorize(chat_id, actor_user_id)
        fact = self.repo._read(chat_id, refs[0]["fact_id"])
        if not fact:
            raise MemoryUnavailable("Selected fact is no longer available")
        if fact["subject_id"] == "GROUP":
            self._authorize(chat_id, actor, admin=True)
            confirmation = AdminConfirmation(actor, True)
        elif fact["subject_id"] == "USER#" + actor:
            confirmation = SelfConfirmation(actor, True)
        else:
            raise MemoryUnavailable("Personal memory can only be changed by its subject")
        return fact, refs[0], confirmation

    def wrong(self, chat_id, actor_user_id, fact_ref):
        fact, ref, confirmation = self._target(chat_id, actor_user_id, fact_ref)
        rejected = self.writer.reject_fact(
            chat_id, fact["fact_id"], expected_fact_version=ref["fact_version"], confirmation=confirmation
        )
        return {
            "state": "REJECTED",
            "fact_ref": {"fact_id": rejected["fact_id"], "fact_version": int(rejected["fact_version"])},
        }

    def correct(self, chat_id, actor_user_id, fact_ref, *, source_event, value):
        fact, ref, confirmation = self._target(chat_id, actor_user_id, fact_ref)
        actor = positive_id(actor_user_id)
        if (
            not isinstance(source_event, SourceEvent)
            or str(source_event.chat_id) != str(chat_id)
            or source_event.actor_user_id != actor
            or source_event.source_kind != "confirmation"
            or source_event.edited_at
            or not isinstance(value, str)
            or not value
            or source_event.text.count(value) != 1
        ):
            raise MemoryInputError("Correction requires this actor's exact command evidence")
        start = source_event.text.index(value)
        evidence = EvidenceSpan(start, start + len(value))
        kind = "admin_confirmed" if isinstance(confirmation, AdminConfirmation) else "self_explicit"
        changes = [FactChange(fact["field"], value, evidence, facet=fact.get("facet", ""), assertion_kind=kind)]
        # A correction to a multi-value slot replaces its selected old value. Other
        # independently confirmed values remain unchanged.
        _, normalised = changes[0].slot(group=kind == "admin_confirmed")
        if fact["field"] in MULTI_FIELDS | GROUP_FIELDS and fact["value"].casefold() != normalised.casefold():
            changes.insert(0, FactChange(fact["field"], fact["value"], evidence, action="remove", assertion_kind=kind))
        for change in changes:
            change.slot(group=kind == "admin_confirmed")
        old_head = self.repo.get_source_head(chat_id, source_event.message_id)
        source = self.repo.register_source(source_event, expected_source_version=int(old_head.get("revision", 0)))
        name = "GROUP" if kind == "admin_confirmed" else actor
        subject = self.repo.get_subject(chat_id, name)
        apply = self.writer.confirm_group_fact if kind == "admin_confirmed" else self.writer.confirm_self_fact
        result = apply(
            chat_id,
            source,
            expected_subject_revision=int(subject["revision"]),
            changes=changes,
            confirmation=confirmation,
            expected_fact=ref,
        )
        return {"state": "CORRECTED", "source_ref": source.as_dict(), "duplicate": result.duplicate}

    def confirm_group(self, chat_id, actor_user_id, *, source_event, field, value):
        actor = self._authorize(chat_id, actor_user_id, admin=True)
        if (
            not isinstance(source_event, SourceEvent)
            or str(source_event.chat_id) != str(chat_id)
            or source_event.actor_user_id != actor
            or source_event.source_kind != "confirmation"
            or source_event.edited_at
            or not isinstance(value, str)
            or not value
            or source_event.text.count(value) != 1
        ):
            raise MemoryInputError("Group confirmation requires a new explicit administrator command")
        start = source_event.text.index(value)
        change = FactChange(field, value, EvidenceSpan(start, start + len(value)), assertion_kind="admin_confirmed")
        change.slot(group=True)
        old = self.repo.get_source_head(chat_id, source_event.message_id)
        ref = self.repo.register_source(source_event, expected_source_version=int(old.get("revision", 0)))
        subject = self.repo.ensure_subject(chat_id, "GROUP")
        result = self.writer.confirm_group_fact(
            chat_id,
            ref,
            expected_subject_revision=int(subject["revision"]),
            changes=[change],
            confirmation=AdminConfirmation(actor, True),
        )
        return {"state": "CONFIRMED", "source_ref": ref.as_dict(), "duplicate": result.duplicate}

    def forget_source(self, chat_id, actor_user_id, source_id):
        actor = self._authorize(chat_id, actor_user_id)
        observation = self.repo.get_observation(chat_id, positive_id(source_id))
        if observation.get("actor_user_id") != actor:
            raise MemoryUnavailable("Only the source author may erase that source")
        return self.lifecycle.begin(chat_id, scope="source", target=source_id)

    def forget_me(self, chat_id, actor_user_id, *, optout=False):
        actor = self._authorize(chat_id, actor_user_id)
        return self.lifecycle.begin(chat_id, scope="subject", target=actor, optout=optout)

    def optout(self, chat_id, actor_user_id):
        return self.forget_me(chat_id, actor_user_id, optout=True)

    def optin(self, chat_id, actor_user_id):
        actor = self._authorize(chat_id, actor_user_id)
        subject = self.repo.get_subject(chat_id, actor)
        if not subject:
            raise MemoryUnavailable("No scoped subject is available to opt in")
        self.repo.opt_in(chat_id, actor, expected_revision=int(subject["revision"]))
        return {"state": "OPTED_IN"}

    def forget_group(self, chat_id, actor_user_id):
        self._authorize(chat_id, actor_user_id, admin=True)
        return self.lifecycle.begin(chat_id, scope="group")
