"""Bounded control-command identity, serialization and interruption recovery.

Receipts contain hashes and control references, never command text or fact values.
They survive scoped erasure for seven days; commands older than one day cannot run.
"""

import hashlib
import json
import uuid

from .models import MemoryConflict, MemoryUnavailable, SourceRef, chat_key, positive_id
from .repository import MemoryRepository, source_hash
from .telegram_ingestion import source_event

COMMAND_LEASE_SECONDS = 360  # Longer than the Bot Lambda's 300-second maximum lifetime.
COMMAND_RETENTION_SECONDS = 7 * 86400


class CommandRetryRequired(RuntimeError):
    """An unfinished command needs redelivery rather than a success acknowledgement."""


def _operation_key(operation):
    value = next(iter(operation.values()))
    row = value.get("Key", value.get("Item", {}))
    return row.get("pk"), row.get("sk")


class _CommandRepository(MemoryRepository):
    """Same domain methods/table with an additional command-owner transaction fence."""

    def __init__(self, owner):
        self.owner, self.table, self.clock = owner, owner.repo.table, owner.repo.clock

    def _transaction(self, operations):
        existing = {_operation_key(operation) for operation in operations}
        checks = [check for check in self.owner.scope_checks() if _operation_key(check) not in existing]
        self.owner.repo._transaction([*operations, *checks, self.owner.lock_check()])


class CommandReceipt:
    def __init__(self, repo, ctx, action, *, fact_ref=None, target_source=None):
        self.repo, self.ctx, self.action = repo, ctx, action
        self.chat, self.actor = str(ctx.chat_id), positive_id(ctx.user_id)
        self.message = positive_id(ctx.message_id)
        self.event = source_event(ctx._update)
        self.original = ctx.message.get("date")
        if (
            self.event is None
            or self.event.edited_at
            or self.event.is_forwarded
            or str(self.event.chat_id) != self.chat
            or self.event.actor_user_id != self.actor
            or self.event.message_id != self.message
            or self.event.original_sent_at != self.original
            or type(self.original) is not int
            or not repo.now() - 86400 <= self.original <= repo.now()
        ):
            raise MemoryUnavailable("Control command requires a recent original group message")
        self.key = "CONTROL_COMMAND#" + self.message.zfill(20)
        self.lock_key = "CONTROL_COMMAND#LOCK"
        self.fact_ref, self.target_source = fact_ref, target_source
        identity = [self.chat, self.actor, self.message, self.original, ctx.text, target_source]
        self.digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        self.row = self.lock = None
        self.fenced_repo = _CommandRepository(self)

    def _purge_key(self):
        if self.action in {"forget_me", "optout"}:
            return "PURGE#SUBJECT#" + self.actor
        if self.action == "forget_group":
            return "PURGE#GROUP#GROUP"
        if self.action == "forget_this":
            return "PURGE#SOURCE#" + positive_id(self.target_source)
        return None

    def _order_key(self):
        if self.action in {"on", "off", "forget_group"}:
            return "CONTROL_COMMAND#ORDER#GROUP"
        if self.action in {"forget_me", "optout", "optin"}:
            return "CONTROL_COMMAND#ORDER#USER#" + self.actor
        return None

    @staticmethod
    def _purge_identity(job):
        return {key: job.get(key) for key in ("epoch", "created_at", "old_generation", "source_version")}

    def acquire(self):
        lock = self.repo._read(self.chat, self.lock_key)
        if lock.get("state") == "ACTIVE" and int(lock.get("lease_until", 0)) > self.repo.now():
            raise CommandRetryRequired("A control command is still in flight")
        old = self.repo._read(self.chat, self.key)
        if old and (old.get("request_hash") != self.digest or old.get("actor_user_id") != self.actor):
            raise MemoryUnavailable("Control command identity changed")
        control, subject = self.repo.get_control(self.chat), self.repo.get_subject(self.chat, self.actor)
        purge_key = self._purge_key()
        purge = self.repo._read(self.chat, purge_key) if purge_key else {}
        row = old or {
            "pk": chat_key(self.chat),
            "sk": self.key,
            "kind": "CONTROL_COMMAND",
            "revision": 0,
            "request_hash": self.digest,
            "actor_user_id": self.actor,
            "requested_at": self.original,
            "epoch": control["epoch"],
            "actor_generation": int(subject.get("generation", 0)),
            "action": self.action,
            "state": "PENDING",
            "fact_ref": self.fact_ref,
            "purge_key": purge_key,
            "purge_previous_revision": int(purge.get("revision", 0)),
            "purge_was_pending": bool(purge and purge.get("state") != "DONE"),
            "purge_previous_identity": self._purge_identity(purge),
            "created_at": self.repo.now(),
            "ttl": self.original + COMMAND_RETENTION_SECONDS,
        }
        token = uuid.uuid4().hex
        self.row = {**row, "revision": int(row["revision"]) + 1}
        self.lock = {
            "pk": chat_key(self.chat),
            "sk": self.lock_key,
            "kind": "CONTROL_COMMAND_LOCK",
            "revision": int(lock.get("revision", 0)) + 1,
            "state": "ACTIVE",
            "token": token,
            "lease_until": self.repo.now() + COMMAND_LEASE_SECONDS,
            "command_key": self.key,
            "ttl": self.repo.now() + COMMAND_RETENTION_SECONDS,
        }
        operations = [self.repo._put_cas(self.lock, lock), self.repo._put_cas(self.row, old)]
        order_key = self._order_key()
        if order_key:
            order = self.repo._read(self.chat, order_key)
            if int(order.get("message_id", 0)) < int(self.message):
                operations.append(
                    self.repo._put_cas(
                        {
                            "pk": chat_key(self.chat),
                            "sk": order_key,
                            "kind": "CONTROL_COMMAND_ORDER",
                            "revision": int(order.get("revision", 0)) + 1,
                            "message_id": int(self.message),
                            "ttl": self.original + COMMAND_RETENTION_SECONDS,
                        },
                        order,
                    )
                )
        try:
            self.repo._transaction(operations)
        except MemoryConflict as exc:
            self.lock = None
            raise CommandRetryRequired("Control command ownership changed") from exc

    def lock_check(self):
        if self.lock is None or self.repo.now() >= self.lock["lease_until"]:
            raise CommandRetryRequired("Control command lease expired")
        check = self.repo._check_snapshot(self.lock)
        value = check["ConditionCheck"]
        value["ConditionExpression"] += " AND #state = :active AND #token = :token AND lease_until > :now"
        value["ExpressionAttributeNames"].update({"#state": "state", "#token": "token"})
        value["ExpressionAttributeValues"].update(
            {":active": "ACTIVE", ":token": self.lock["token"], ":now": self.repo.now()}
        )
        return check

    def _check_or_absent(self, row, sk):
        if row:
            return self.repo._check_snapshot(row)
        return {
            "ConditionCheck": {
                "TableName": self.repo.table.name,
                "Key": {"pk": chat_key(self.chat), "sk": sk},
                "ConditionExpression": "attribute_not_exists(pk)",
            }
        }

    def scope_checks(self):
        """Called before every domain transaction, including preparatory source writes."""
        control = self.repo.get_control(self.chat)
        subject = self.repo.get_subject(self.chat, self.actor)
        if (
            control["epoch"] != self.row["epoch"]
            or int(subject.get("generation", 0)) != self.row["actor_generation"]
            or self.original < int(control.get("learning_started_at", 0))
            or self.original < int(subject.get("learning_started_at", 0))
            or not self.repo.now() - 86400 <= self.original <= self.repo.now()
        ):
            raise MemoryUnavailable("Control command predates the current memory scope")
        observation = self.repo.get_observation(self.chat, self.message)
        if observation and (
            observation.get("deleted")
            or observation.get("ambiguous")
            or observation.get("edited_at")
            or observation.get("epoch") != control["epoch"]
            or observation.get("actor_user_id") != self.actor
            or observation.get("original_sent_at") != self.original
            or observation.get("content_hash")
            != source_hash(self.event.text, self.event.quoted_spans, self.event.source_kind)
        ):
            raise MemoryUnavailable("Control command source was changed or erased")
        # get_control's synthetic STOPPED row is not a persisted revision-zero item.
        persisted_control = self.repo._read(self.chat, "CONTROL")
        checks = [
            self._check_or_absent(persisted_control, "CONTROL"),
            self._check_or_absent(subject, self.repo.subject_key(self.actor)),
            self._check_or_absent(observation, "OBSERVATION#" + self.message),
        ]
        order_key = self._order_key()
        if order_key:
            order = self.repo._read(self.chat, order_key)
            if int(order.get("message_id", 0)) != int(self.message):
                raise MemoryUnavailable("A newer control command superseded this request")
            checks.append(self.repo._check_snapshot(order))
        return checks

    def _saved_result(self):
        if self.row.get("result_purge_key"):
            job = self.repo._read(self.chat, self.row["result_purge_key"])
            if job and self._purge_identity(job) == self.row.get("result_purge_identity"):
                return job
            return {"state": "DONE"}  # Never advance a later generation reusing this job key.
        return {"state": self.row["result_state"]}

    def recover(self):
        if self.row["state"] == "APPLIED":
            return self._saved_result()
        if self.row["state"] != "PENDING":
            raise MemoryUnavailable("Control command is no longer actionable")
        result = None
        purge_key = self.row.get("purge_key")
        if purge_key:
            job = self.repo._read(self.chat, purge_key)
            if self.action == "forget_this" and job and job.get("actor_user_id") != self.actor:
                raise MemoryUnavailable("Only the source author may recover this deletion")
            initial = self.row["purge_previous_identity"]
            same_pending = self.row["purge_was_pending"] and self._purge_identity(job) == initial
            newly_started = (
                job.get("epoch") == self.row["epoch"]
                and int(job.get("revision", 0)) > self.row["purge_previous_revision"]
                and int(job.get("created_at", -1)) >= self.row["created_at"]
            )
            if self.action in {"forget_me", "optout"} and newly_started:
                newly_started = job.get("old_generation") == self.row["actor_generation"]
            if (same_pending or newly_started) and (self.action != "optout" or job.get("optout")):
                result = job
        elif self.action in {"correct", "confirm_group"}:
            head = self.repo.get_source_head(self.chat, self.message)
            if head and head.get("epoch") == self.row["epoch"] and head.get("source_kind") == "confirmation":
                ref = SourceRef(self.message, int(head["revision"]), head["epoch"])
                work = self.repo.get_work(self.chat, ref)
                if work.get("state") == "DONE" and head.get("actor_user_id") == self.actor:
                    result = {"state": "CORRECTED" if self.action == "correct" else "CONFIRMED"}
        elif self.action == "wrong":
            fact = self.repo._read(self.chat, self.fact_ref["fact_id"])
            if (
                fact.get("status") == "REJECTED"
                and fact.get("rejected_fact_version") == self.fact_ref["fact_version"]
                and fact.get("rejected_by") == self.actor
            ):
                result = {"state": "REJECTED"}
        else:
            control = self.repo.get_control(self.chat)
            if (
                self.action in {"on", "off"}
                and control["state"] == "ACTIVE"
                and control["learning_enabled"] == (self.action == "on")
            ):
                result = {"state": "LEARNING_ON" if self.action == "on" else "LEARNING_OFF"}
            elif self.action == "optin":
                subject = self.repo.get_subject(self.chat, self.actor)
                if (
                    subject.get("state") == "ACTIVE"
                    and subject.get("epoch") == self.row["epoch"]
                    and subject.get("generation") == self.row["actor_generation"]
                    and subject.get("optout") is False
                ):
                    result = {"state": "OPTED_IN"}
        if result is not None:
            return self.complete(result)
        self.scope_checks()
        return None

    def complete(self, result):
        updated = {
            **self.row,
            "revision": int(self.row["revision"]) + 1,
            "state": "APPLIED",
            "result_state": result["state"],
        }
        if result.get("kind") == "PURGE":
            updated.update(result_purge_key=result["sk"], result_purge_identity=self._purge_identity(result))
        self.repo._transaction([self.lock_check(), self.repo._put_cas(updated, self.row)])
        self.row = updated
        return result

    def release(self):
        if self.lock is None:
            return
        updated = {**self.lock, "revision": int(self.lock["revision"]) + 1, "state": "RELEASED"}
        try:
            self.repo._transaction([self.repo._put_cas(updated, self.lock)])
        except MemoryConflict:
            pass  # An expired owner must never release its successor's command lease.
        self.lock = None
