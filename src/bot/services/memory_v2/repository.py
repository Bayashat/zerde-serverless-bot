"""Sole Memory V2 control/source repository; profile reads only current facts."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from services.repositories._common import get_dynamodb

from .models import (
    FRESHNESS_SECONDS,
    RAW_RETENTION_SECONDS,
    SINGLE_FIELDS,
    WORK_RETENTION_SECONDS,
    MemoryConflict,
    MemoryInputError,
    MemoryUnavailable,
    SourceEvent,
    SourceRef,
    chat_key,
    integer,
    positive_id,
    work_queue,
)


def source_hash(text, quoted_spans, source_kind):
    document = {"text": text, "quoted_spans": [[int(a), int(b)] for a, b in quoted_spans], "source_kind": source_kind}
    return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class MemoryRepository:
    def __init__(self, table_name: str, *, clock: Callable[[], float] = time.time):
        if not isinstance(table_name, str) or not table_name.strip():
            raise MemoryInputError("An explicit independent Memory V2 table is required")
        self.table = get_dynamodb().Table(table_name)
        self.clock = clock

    def now(self) -> int:
        return int(self.clock())

    def _read(self, chat_id, sk):
        response = self.table.get_item(Key={"pk": chat_key(chat_id), "sk": sk}, ConsistentRead=True)
        return response.get("Item") or {}

    def _transaction(self, operations):
        try:
            # Resource client owns serialization, including transaction values.
            self.table.meta.client.transact_write_items(TransactItems=operations)
        except ClientError as exc:
            reasons = exc.response.get("CancellationReasons") or []
            if exc.response.get("Error", {}).get("Code") == "TransactionCanceledException" and any(
                reason.get("Code") == "ConditionalCheckFailed" for reason in reasons
            ):
                raise MemoryConflict("Memory snapshot changed") from exc
            raise

    def _put_cas(self, item, previous):
        operation = {"TableName": self.table.name, "Item": item}
        if previous:
            operation.update(
                ConditionExpression="#revision = :revision",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": previous["revision"]},
            )
        else:
            operation["ConditionExpression"] = "attribute_not_exists(pk)"
        return {"Put": operation}

    def _check_snapshot(self, item):
        return {
            "ConditionCheck": {
                "TableName": self.table.name,
                "Key": {"pk": item["pk"], "sk": item["sk"]},
                "ConditionExpression": "#revision = :revision",
                "ExpressionAttributeNames": {"#revision": "revision"},
                "ExpressionAttributeValues": {":revision": item["revision"]},
            }
        }

    def get_control(self, chat_id):
        return self._read(chat_id, "CONTROL") or {
            "pk": chat_key(chat_id),
            "sk": "CONTROL",
            "state": "STOPPED",
            "learning_enabled": False,
            "epoch": "",
            "learning_started_at": 0,
            "revision": 0,
        }

    def _active_control(self, chat_id, *, learning=False):
        control = self.get_control(chat_id)
        if control["state"] != "ACTIVE" or (learning and not control["learning_enabled"]):
            raise MemoryUnavailable("Group memory is not active for this operation")
        return control

    def activate_group(self, chat_id, *, expected_revision: int):
        previous = self._read(chat_id, "CONTROL")
        if int(previous.get("revision", 0)) != expected_revision or previous.get("state", "STOPPED") != "STOPPED":
            raise MemoryConflict("Group activation requires current stopped revision")
        item = {
            "pk": chat_key(chat_id),
            "sk": "CONTROL",
            "state": "ACTIVE",
            "learning_enabled": True,
            "epoch": uuid.uuid4().hex,
            "learning_started_at": self.now(),
            "revision": expected_revision + 1,
        }
        self._transaction([self._put_cas(item, previous)])
        return item

    def _change_control(self, chat_id, expected_revision, old_state, **changes):
        previous = self.get_control(chat_id)
        if previous["revision"] != expected_revision or previous["state"] != old_state:
            raise MemoryConflict("Unexpected group control state")
        item = {**previous, **changes, "revision": expected_revision + 1}
        self._transaction([self._put_cas(item, previous)])
        return item

    def set_learning_enabled(self, chat_id, enabled: bool, *, expected_revision: int):
        if not isinstance(enabled, bool):
            raise MemoryInputError("Learning flag must be boolean")
        return self._change_control(chat_id, expected_revision, "ACTIVE", learning_enabled=enabled)

    def begin_group_stop(self, chat_id, *, expected_revision: int):
        return self._change_control(chat_id, expected_revision, "ACTIVE", state="STOPPING", learning_enabled=False)

    def complete_group_stop(self, chat_id, *, expected_revision: int):
        """Z09 may call only after its registered answer leases have drained."""
        return self._change_control(chat_id, expected_revision, "STOPPING", state="STOPPED", learning_enabled=False)

    @staticmethod
    def subject_key(user_id):
        return "SUBJECT#GROUP" if user_id == "GROUP" else f"SUBJECT#USER#{positive_id(user_id)}"

    def get_subject(self, chat_id, user_id):
        return self._read(chat_id, self.subject_key(user_id))

    def _ensure_subject(self, chat_id, user_id, control):
        previous = self.get_subject(chat_id, user_id)
        if previous and previous.get("epoch") == control["epoch"]:
            return previous
        # A new group epoch isolates every old generation; retain explicit optout.
        subject = {
            "pk": chat_key(chat_id),
            "sk": self.subject_key(user_id),
            "state": "ACTIVE",
            "epoch": control["epoch"],
            "generation": int(previous.get("generation", 0)),
            "optout": bool(previous.get("optout", False)),
            "learning_started_at": control["learning_started_at"],
            "revision": int(previous.get("revision", 0)) + 1,
        }
        self._transaction([self._check_snapshot(control), self._put_cas(subject, previous)])
        return subject

    def ensure_subject(self, chat_id, user_id):
        return self._ensure_subject(chat_id, user_id, self._active_control(chat_id))

    def _active_subject(self, chat_id, user_id, control):
        subject = self.get_subject(chat_id, user_id)
        if not subject or subject.get("epoch") != control["epoch"] or subject["state"] != "ACTIVE" or subject["optout"]:
            raise MemoryUnavailable("Subject memory is unavailable")
        return subject

    def begin_subject_stop(self, chat_id, user_id, *, expected_revision: int, optout=False):
        control = self._active_control(chat_id)
        previous = self._ensure_subject(chat_id, user_id, control)
        if previous["revision"] != expected_revision or previous["state"] != "ACTIVE":
            raise MemoryConflict("Unexpected subject control state")
        item = {
            **previous,
            "state": "STOPPING",
            "optout": bool(optout or previous["optout"]),
            "generation": int(previous["generation"]) + 1,
            "revision": expected_revision + 1,
            "learning_started_at": self.now(),
        }
        self._transaction([self._check_snapshot(control), self._put_cas(item, previous)])
        return item

    def complete_subject_stop(self, chat_id, user_id, *, expected_revision: int):
        """Control fence only; Z09 owns clearing data and draining answer leases."""
        control = self._active_control(chat_id)
        previous = self.get_subject(chat_id, user_id)
        if not previous or previous["revision"] != expected_revision or previous["state"] != "STOPPING":
            raise MemoryConflict("Unexpected subject stop revision")
        item = {**previous, "state": "ACTIVE", "learning_started_at": self.now(), "revision": expected_revision + 1}
        self._transaction([self._check_snapshot(control), self._put_cas(item, previous)])
        return item

    def opt_in(self, chat_id, user_id, *, expected_revision: int):
        control = self._active_control(chat_id)
        previous = self.get_subject(chat_id, user_id)
        if not previous or previous["revision"] != expected_revision or previous["state"] != "ACTIVE":
            raise MemoryConflict("Unexpected subject opt-in revision")
        item = {**previous, "optout": False, "learning_started_at": self.now(), "revision": expected_revision + 1}
        self._transaction([self._check_snapshot(control), self._put_cas(item, previous)])
        return item

    @staticmethod
    def work_key(ref: SourceRef):
        return f"WORK#{ref.source_id}#{ref.source_version}"

    def get_source_head(self, chat_id, source_id):
        return self._read(chat_id, f"HEAD#{positive_id(source_id)}")

    def get_work(self, chat_id, ref: SourceRef):
        return self._read(chat_id, self.work_key(ref))

    def register_source(self, event: SourceEvent, *, expected_source_version=0) -> SourceRef:
        """Atomically accept safe source + RAW + PENDING. Z06 adds transport only."""
        from .safety import require_public_content

        event.validate()
        integer(expected_source_version)
        require_public_content(event.text, max_length=20000)
        control = self._active_control(event.chat_id, learning=event.source_kind == "message")
        now = self.now()
        expires_at = event.original_sent_at + RAW_RETENTION_SECONDS
        if event.original_sent_at < control["learning_started_at"] or event.original_sent_at > now or expires_at <= now:
            raise MemoryUnavailable("Source is outside the active learning window")
        subject = self._ensure_subject(event.chat_id, event.actor_user_id, control)
        if subject["state"] != "ACTIVE" or subject["optout"] or event.original_sent_at < subject["learning_started_at"]:
            raise MemoryUnavailable("Source predates subject activation or opt-in")
        old = self.get_source_head(event.chat_id, event.message_id)
        digest = source_hash(event.text, event.quoted_spans, event.source_kind)
        if old:
            if old["epoch"] != control["epoch"] or old["deleted"] or old["subject_generation"] != subject["generation"]:
                raise MemoryUnavailable("Old source identity cannot be revived")
            if (
                old["actor_user_id"] != str(event.actor_user_id)
                or old["original_sent_at"] != event.original_sent_at
                or old["source_kind"] != event.source_kind
            ):
                raise MemoryInputError("Immutable source identity changed")
            if old["content_hash"] == digest and old["edited_at"] == event.edited_at:
                return SourceRef(str(event.message_id), int(old["revision"]), old["epoch"])
            if event.edited_at <= old["edited_at"]:
                raise MemoryConflict("Old or ambiguous same-time edit")
        if int(old.get("revision", 0)) != expected_source_version:
            raise MemoryConflict("Unexpected source revision")
        version = expected_source_version + 1
        ref = SourceRef(str(event.message_id), version, control["epoch"])
        common = {
            "pk": chat_key(event.chat_id),
            "source_id": str(event.message_id),
            "revision": version,
            "epoch": ref.epoch,
            "actor_user_id": str(event.actor_user_id),
            "subject_generation": subject["generation"],
            "original_sent_at": event.original_sent_at,
            "edited_at": event.edited_at,
            "content_hash": digest,
            "expires_at": expires_at,
            "source_kind": event.source_kind,
        }
        head = {
            **common,
            "sk": f"HEAD#{event.message_id}",
            "deleted": False,
            "retained_evidence": bool(old.get("retained_evidence", False)),
        }
        if not head["retained_evidence"]:
            head["ttl"] = expires_at
        raw = {
            **common,
            "sk": f"RAW#{event.message_id}",
            "text": event.text,
            "quoted_spans": [list(span) for span in event.quoted_spans],
            "ttl": expires_at,
        }
        work = {
            "pk": chat_key(event.chat_id),
            "sk": self.work_key(ref),
            "revision": 1,
            "source_ref": ref.as_dict(),
            "actor_user_id": str(event.actor_user_id),
            "subject_generation": subject["generation"],
            "state": "PENDING",
            "lease_token": "",
            "lease_until": 0,
            "attempts": 0,
            "next_attempt_at": now,
            "due_at": now,
            "work_queue": work_queue(event.chat_id),
            "expires_at": expires_at,
            "ttl": expires_at + WORK_RETENTION_SECONDS,
        }
        changed_subject = {**subject, "revision": int(subject["revision"]) + 1}
        if expires_at <= self.now():
            raise MemoryUnavailable("Source expired during registration")
        self._transaction(
            [
                self._check_snapshot(control),
                self._put_cas(changed_subject, subject),
                self._put_cas(head, old),
                {"Put": {"TableName": self.table.name, "Item": raw}},
                self._put_cas(work, {}),
            ]
        )
        return ref

    def source_snapshot(self, chat_id, ref: SourceRef, *, learning=True):
        control = self._active_control(chat_id, learning=learning)
        head = self.get_source_head(chat_id, ref.source_id)
        raw = self._read(chat_id, f"RAW#{ref.source_id}")
        if (
            not head
            or not raw
            or head.get("deleted")
            or head.get("epoch") != ref.epoch
            or control["epoch"] != ref.epoch
        ):
            raise MemoryUnavailable("Source is missing or obsolete")
        if head["revision"] != ref.source_version or raw["revision"] != ref.source_version or raw["epoch"] != ref.epoch:
            raise MemoryUnavailable("Source revision changed")
        if head["content_hash"] != source_hash(raw["text"], raw["quoted_spans"], raw["source_kind"]):
            raise MemoryUnavailable("Source content hash mismatch")
        subject = self._active_subject(chat_id, head["actor_user_id"], control)
        now = self.now()
        if (
            head["subject_generation"] != subject["generation"]
            or raw["actor_user_id"] != head["actor_user_id"]
            or int(head["expires_at"]) <= now
            or int(raw["expires_at"]) <= now
        ):
            raise MemoryUnavailable("Source is expired or belongs to an old subject generation")
        return control, subject, head, raw

    def _list(self, chat_id, prefix):
        key = None
        while True:
            args = {
                "KeyConditionExpression": Key("pk").eq(chat_key(chat_id)) & Key("sk").begins_with(prefix),
                "ConsistentRead": True,
                "Limit": 100,
            }
            if key:
                args["ExclusiveStartKey"] = key
            response = self.table.query(**args)
            yield from response.get("Items", [])
            key = response.get("LastEvaluatedKey")
            if not key:
                return

    def get_profile(self, chat_id, user_id):
        """Return validated facts and freshness labels; no independent profile writer."""
        control = self._active_control(chat_id)
        subject = self._active_subject(chat_id, user_id, control)
        name = "GROUP" if user_id == "GROUP" else f"USER#{positive_id(user_id)}"
        facts = []
        owners = {}
        now = self.now()
        for fact in self._list(chat_id, f"FACT#{name}#"):
            if (
                fact.get("status") != "ACTIVE"
                or fact.get("epoch") != control["epoch"]
                or fact.get("subject_generation") != subject["generation"]
            ):
                continue
            if int(fact.get("valid_from", now + 1)) > now:
                continue
            ref = fact["evidence"]["source_ref"]
            head = self.get_source_head(chat_id, ref["source_id"])
            if (
                not head
                or not head.get("retained_evidence")
                or head.get("deleted")
                or head.get("revision") != ref["source_version"]
                or head.get("epoch") != ref["epoch"]
            ):
                continue
            owner = self.get_subject(chat_id, head["actor_user_id"])
            if (
                not owner
                or owner["state"] != "ACTIVE"
                or owner["optout"]
                or owner["generation"] != head["subject_generation"]
                or owner["epoch"] != control["epoch"]
            ):
                continue
            owners[head["actor_user_id"]] = owner
            stale = fact["field"] in SINGLE_FIELDS and now - int(fact["last_confirmed_at"]) >= FRESHNESS_SECONDS
            facts.append({**fact, "freshness": "last_confirmed" if stale else "current"})
        if (
            self.get_control(chat_id)["revision"] != control["revision"]
            or self.get_subject(chat_id, user_id)["revision"] != subject["revision"]
        ):
            raise MemoryConflict("Profile changed during read")
        if any(
            self.get_subject(chat_id, actor)["revision"] != snapshot["revision"] for actor, snapshot in owners.items()
        ):
            raise MemoryConflict("Profile evidence changed during read")
        return facts
