"""The sole writer of V2 facts. Extraction commits require a live work lease."""

from __future__ import annotations

from .models import (
    HISTORY_RETENTION_SECONDS,
    WORK_RETENTION_SECONDS,
    AdminConfirmation,
    CommitResult,
    EvidenceSpan,
    FactChange,
    MemoryConflict,
    MemoryInputError,
    MemoryUnavailable,
    SelfConfirmation,
    SourceRef,
    WorkLease,
    integer,
    positive_id,
)
from .repository import MemoryRepository
from .safety import require_preference_name, require_public_content


class FactWriter:
    def __init__(self, repo: MemoryRepository):
        self.repo = repo

    def apply_source_changes(
        self,
        chat_id,
        source_ref: SourceRef,
        *,
        subject_generation: int,
        expected_subject_revision: int,
        changes: list[FactChange],
        lease: WorkLease,
    ) -> CommitResult:
        if (
            not isinstance(lease, WorkLease)
            or lease.source_ref != source_ref
            or lease.subject_generation != subject_generation
        ):
            raise MemoryInputError("Fact extraction requires the matching work lease")
        return self._apply(chat_id, source_ref, changes, expected_subject_revision, subject_generation, lease=lease)

    def confirm_group_fact(
        self,
        chat_id,
        source_ref: SourceRef,
        *,
        expected_subject_revision: int,
        changes: list[FactChange],
        confirmation: AdminConfirmation,
        expected_fact=None,
    ) -> CommitResult:
        if not isinstance(confirmation, AdminConfirmation) or confirmation.confirmed is not True:
            raise MemoryInputError("Group facts require trusted explicit administrator confirmation")
        positive_id(confirmation.actor_user_id)
        return self._apply(
            chat_id,
            source_ref,
            changes,
            expected_subject_revision,
            None,
            confirmation=confirmation,
            expected_fact=expected_fact,
        )

    def confirm_self_fact(
        self, chat_id, source_ref, *, expected_subject_revision, changes, confirmation, expected_fact=None
    ):
        if not isinstance(confirmation, SelfConfirmation) or confirmation.confirmed is not True:
            raise MemoryInputError("Personal corrections require authenticated self confirmation")
        positive_id(confirmation.actor_user_id)
        return self._apply(
            chat_id,
            source_ref,
            changes,
            expected_subject_revision,
            None,
            confirmation=confirmation,
            expected_fact=expected_fact,
        )

    def reject_fact(self, chat_id, fact_id, *, expected_fact_version, confirmation):
        """Reject one fact version without resetting its ordering or prior feedback."""
        if not isinstance(confirmation, (SelfConfirmation, AdminConfirmation)) or confirmation.confirmed is not True:
            raise MemoryInputError("Fact rejection requires authenticated confirmation")
        actor = positive_id(confirmation.actor_user_id)
        integer(expected_fact_version, minimum=1)
        if not isinstance(fact_id, str) or not fact_id.startswith("FACT#"):
            raise MemoryInputError("Expected a fact identity")
        control = self.repo._active_control(chat_id)
        old = self.repo._read(chat_id, fact_id)
        if not old or old.get("epoch") != control["epoch"]:
            raise MemoryUnavailable("Fact is not current")
        personal = old["subject_id"] == "USER#" + actor
        group = old["subject_id"] == "GROUP" and isinstance(confirmation, AdminConfirmation)
        if not (personal or group):
            raise MemoryInputError("Cannot reject another person's fact")
        subject = self.repo._active_subject(chat_id, "GROUP" if group else actor, control)
        if old["subject_generation"] != subject["generation"]:
            raise MemoryUnavailable("Fact belongs to a deleted generation")
        if old.get("rejected_fact_version") == expected_fact_version and old["status"] == "REJECTED":
            return old
        if old["revision"] != expected_fact_version or old["status"] != "ACTIVE":
            raise MemoryConflict("Fact version changed before rejection")
        updated = {
            **old,
            "revision": int(old["revision"]) + 1,
            "fact_version": int(old["revision"]) + 1,
            "status": "REJECTED",
            "rejected_fact_version": expected_fact_version,
            "wrong_feedback_count": int(old.get("wrong_feedback_count", 0)) + 1,
            "feedback_status": "WRONG",
            "rejected_at": self.repo.now(),
            "rejected_by": actor,
        }
        self.repo._transaction(
            [
                self.repo._check_snapshot(control),
                self.repo._put_cas({**subject, "revision": int(subject["revision"]) + 1}, subject),
                self.repo._put_cas(updated, old),
            ]
        )
        return updated

    def _apply(
        self, chat_id, ref, changes, expected_revision, generation, *, lease=None, confirmation=None, expected_fact=None
    ):
        if not isinstance(ref, SourceRef) or not isinstance(changes, list) or len(changes) > 16:
            raise MemoryInputError("Invalid fact commit size or identity")
        group = isinstance(confirmation, AdminConfirmation)
        explicit = confirmation is not None
        work = self.repo.get_work(chat_id, ref)
        if not work or work.get("source_ref") != ref.as_dict():
            raise MemoryUnavailable("Source work is missing or obsolete")
        if work["state"] == "DONE":
            return CommitResult(ref, (), duplicate=True)
        control, author, head, raw = self.repo.source_snapshot(chat_id, ref, learning=not explicit)
        if explicit:
            if head["source_kind"] != "confirmation" or head["actor_user_id"] != confirmation.actor_user_id:
                raise MemoryInputError("Confirmation must reference the authorized actor's explicit command")
            subject = self.repo._ensure_subject(chat_id, "GROUP", control) if group else author
            if work["state"] != "PENDING":
                raise MemoryConflict("Confirmation source work is already owned")
            name = "GROUP" if group else f"USER#{head['actor_user_id']}"
        else:
            if head["source_kind"] != "message" or work["state"] != "LEASED" or work["lease_token"] != lease.token:
                raise MemoryUnavailable("Extraction lease is no longer owned")
            subject = author
            name = f"USER#{head['actor_user_id']}"
            if subject["generation"] != generation or work["subject_generation"] != generation:
                raise MemoryUnavailable("Subject generation changed")
        if subject["state"] != "ACTIVE" or subject["optout"] or subject["revision"] != expected_revision:
            raise MemoryConflict("Subject state changed before fact commit")
        order = [int(head["original_sent_at"]), int(ref.source_id), int(head["edited_at"]), ref.source_version]
        operations, written, skipped, seen = [], [], [], set()
        # No caller-provided pre-model timestamp: expiry and history retention use
        # the clock at the commit attempt, and are rechecked immediately below.
        now = self.repo.now()
        for change in changes:
            if not isinstance(change, FactChange) or not isinstance(change.evidence, EvidenceSpan):
                raise MemoryInputError("Expected typed fact change")
            slot, value = change.slot(group=group)
            if change.assertion_kind == "ambiguous":
                skipped.append("ambiguous")
                continue
            expected_kind = "admin_confirmed" if group else "self_explicit"
            if change.assertion_kind != expected_kind:
                raise MemoryInputError("Unsupported assertion attribution")
            require_public_content(value, max_length=160)
            if change.field == "communication_preferences" and change.facet == "name":
                require_preference_name(value)
            if change.field == "location" and any(char.isdigit() for char in value):
                raise MemoryInputError("Only city-level location is supported")
            excerpt = change.evidence.excerpt(raw)
            require_public_content(excerpt, max_length=240)
            observed = int(head["edited_at"] or head["original_sent_at"])
            valid_from = observed if change.valid_from is None else change.valid_from
            if (
                isinstance(valid_from, bool)
                or not isinstance(valid_from, int)
                or valid_from < 1
                or valid_from > observed
            ):
                raise MemoryInputError("Future or unsupported validity interval")
            key = f"FACT#{name}#{change.field}#{slot}"
            if key in seen:
                raise MemoryInputError("Conflicting changes to one fact slot")
            seen.add(key)
            old = self.repo._read(chat_id, key)
            if (
                expected_fact
                and key == expected_fact["fact_id"]
                and old.get("revision") != expected_fact["fact_version"]
            ):
                raise MemoryConflict("Correction targets a changed fact version")
            current = (
                old if old.get("epoch") == ref.epoch and old.get("subject_generation") == subject["generation"] else {}
            )
            if current and tuple(order) <= tuple(int(part) for part in current["source_order"]):
                skipped.append("older_source")
                continue
            if current and change.action == "remove" and current["value"].casefold() != value.casefold():
                skipped.append("different_current_value")
                continue
            version = int(old.get("revision", 0)) + 1
            fact = {
                "pk": head["pk"],
                "sk": key,
                "fact_id": key,
                "subject_id": name,
                "field": change.field,
                "facet": change.facet,
                "value": value,
                "status": "ACTIVE" if change.action == "assert" else "RETRACTED",
                "revision": version,
                "fact_version": version,
                "epoch": ref.epoch,
                "subject_generation": subject["generation"],
                "source_order": order,
                "observed_at": observed,
                "valid_from": valid_from,
                "last_confirmed_at": observed,
                "evidence": {"source_ref": ref.as_dict(), "excerpt": excerpt, "actor_user_id": head["actor_user_id"]},
                "supersedes": f"{key}@{current['revision']}" if current else "",
            }
            if group:
                fact["confirmed_by"] = head["actor_user_id"]
            if current:
                history = {
                    **current,
                    "sk": f"HISTORY#{key}#{int(current['revision']):010d}",
                    "status": "SUPERSEDED",
                    "superseded_by": f"{key}@{version}",
                    "superseded_at": now,
                    "ttl": now + HISTORY_RETENTION_SECONDS,
                }
                operations.append(self.repo._put_cas(history, {}))
            operations.append(self.repo._put_cas(fact, old))
            written.append(key)
        if expected_fact and expected_fact["fact_id"] not in seen:
            raise MemoryInputError("Correction did not address its selected fact")
        # Re-read time after validation/lookups (and after the caller's model
        # request). DDB conditions use this fresh value, not the lease start.
        now = self.repo.now()
        if int(head["expires_at"]) <= now or int(raw["expires_at"]) <= now or int(work["expires_at"]) <= now:
            raise MemoryUnavailable("Source work expired before commit")
        if not explicit and (int(work["lease_until"]) <= now or lease.lease_until != work["lease_until"]):
            raise MemoryUnavailable("Extraction lease expired before commit")
        changed_subject = {**subject, "revision": int(subject["revision"]) + 1}
        guard_operations = [self.repo._check_snapshot(control), self.repo._put_cas(changed_subject, subject)]
        if group:
            guard_operations.append(self.repo._check_snapshot(author))
        head_operation = {
            "TableName": self.repo.table.name,
            "Key": {"pk": head["pk"], "sk": head["sk"]},
            "ConditionExpression": (
                "#revision = :revision AND epoch = :epoch AND deleted = :false "
                "AND expires_at > :now AND subject_generation = :generation"
            ),
            "ExpressionAttributeNames": {"#revision": "revision"},
            "ExpressionAttributeValues": {
                ":revision": ref.source_version,
                ":epoch": ref.epoch,
                ":false": False,
                ":now": now,
                ":generation": author["generation"],
            },
        }
        if written:
            head_operation.update(UpdateExpression="SET retained_evidence = :true REMOVE #ttl")
            head_operation["ExpressionAttributeNames"]["#ttl"] = "ttl"
            head_operation["ExpressionAttributeValues"][":true"] = True
            guard_operations.append({"Update": head_operation})
        else:
            guard_operations.append({"ConditionCheck": head_operation})
        observation = self.repo.get_observation(chat_id, ref.source_id)
        if (
            not observation
            or observation.get("ambiguous")
            or observation["revision"] != ref.source_version
            or observation["epoch"] != ref.epoch
        ):
            raise MemoryUnavailable("Source was edited before fact commit")
        observation_operation = {
            "TableName": self.repo.table.name,
            "Key": {"pk": head["pk"], "sk": observation["sk"]},
            "ConditionExpression": (
                "#revision = :revision AND epoch = :epoch AND deleted = :false AND #ambiguous = :false"
            ),
            "ExpressionAttributeNames": {"#revision": "revision", "#ambiguous": "ambiguous"},
            "ExpressionAttributeValues": {":revision": ref.source_version, ":epoch": ref.epoch, ":false": False},
        }
        if written:
            observation_operation["UpdateExpression"] = "SET retained_evidence = :true REMOVE #ttl"
            observation_operation["ExpressionAttributeNames"]["#ttl"] = "ttl"
            observation_operation["ExpressionAttributeValues"][":true"] = True
            guard_operations.append({"Update": observation_operation})
        else:
            guard_operations.append({"ConditionCheck": observation_operation})
        done = {
            "TableName": self.repo.table.name,
            "Key": {"pk": work["pk"], "sk": work["sk"]},
            "UpdateExpression": (
                "SET #state = :done, completed_at = :now, #ttl = :ttl, "
                "#revision = #revision + :one REMOVE work_queue, due_at"
            ),
            "ConditionExpression": "#revision = :revision AND #state = :expected AND expires_at > :now",
            "ExpressionAttributeNames": {"#state": "state", "#ttl": "ttl", "#revision": "revision"},
            "ExpressionAttributeValues": {
                ":done": "DONE",
                ":now": now,
                ":ttl": now + WORK_RETENTION_SECONDS,
                ":one": 1,
                ":revision": work["revision"],
                ":expected": "PENDING" if explicit else "LEASED",
            },
        }
        if not explicit:
            done["ConditionExpression"] += " AND lease_token = :token AND lease_until > :now"
            done["ExpressionAttributeValues"][":token"] = lease.token
        guard_operations.append({"Update": done})
        guard_operations.append(self.repo._coverage_operation(chat_id, "work_done"))
        self.repo._transaction([*guard_operations, *operations])
        return CommitResult(ref, tuple(written), tuple(skipped))
