"""Sole Memory V2 control/source repository; profile reads only current facts."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable

from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError
from services.repositories._common import get_dynamodb

from .models import (
    CANDIDATE_RETENTION_SECONDS,
    FRESHNESS_SECONDS,
    RAW_RETENTION_SECONDS,
    SINGLE_FIELDS,
    WORK_INDEX_NAME,
    WORK_LEASE_SECONDS,
    WORK_RETENTION_SECONDS,
    WORK_SHARDS,
    ExtractionSource,
    MemoryConflict,
    MemoryInputError,
    MemoryLearningPaused,
    MemorySourceConflict,
    MemoryUnavailable,
    SourceEvent,
    SourceRef,
    WorkLease,
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

    def get_observation(self, chat_id, source_id):
        return self._read(chat_id, f"OBSERVATION#{positive_id(source_id)}")

    def observe(self, event: SourceEvent) -> SourceRef:
        """Advance metadata before moderation, even for an empty/unsafe edit."""
        event.validate_identity()
        control = self._active_control(event.chat_id, learning=False)
        now = self.now()
        if event.original_sent_at < control["learning_started_at"] or event.original_sent_at > now:
            raise MemoryUnavailable("Observation is outside the activation window")
        if event.edited_at > now:
            raise MemoryInputError("Edit time is in the future")
        subject = self._ensure_subject(event.chat_id, event.actor_user_id, control)
        if subject["state"] != "ACTIVE" or subject["optout"] or event.original_sent_at < subject["learning_started_at"]:
            raise MemoryUnavailable("Observation belongs to an unavailable subject")
        old = self.get_observation(event.chat_id, event.message_id)
        digest = source_hash(event.text, event.quoted_spans, event.source_kind)
        ambiguous = False
        if old:
            if old["epoch"] != control["epoch"] or old["deleted"] or old["subject_generation"] != subject["generation"]:
                raise MemoryUnavailable("An obsolete source cannot be revived")
            if (
                old["actor_user_id"] != str(event.actor_user_id)
                or old["original_sent_at"] != event.original_sent_at
                or old["source_kind"] != event.source_kind
            ):
                raise MemoryInputError("Immutable observation identity changed")
            if old.get("ambiguous") and event.edited_at <= old["edited_at"]:
                raise MemorySourceConflict("Source remains ambiguous until a strictly later edit")
            if old["content_hash"] == digest and old["edited_at"] == event.edited_at:
                return SourceRef(str(event.message_id), int(old["revision"]), old["epoch"])
            if event.edited_at < old["edited_at"]:
                raise MemorySourceConflict("Old observation cannot replace a newer source")
            ambiguous = event.edited_at == old["edited_at"]
        elif event.original_sent_at + RAW_RETENTION_SECONDS <= now:
            raise MemoryUnavailable("Unobserved source is already expired")
        version = int(old.get("revision", 0)) + 1
        item = {
            "pk": chat_key(event.chat_id),
            "sk": f"OBSERVATION#{event.message_id}",
            "source_id": str(event.message_id),
            "revision": version,
            "epoch": control["epoch"],
            "actor_user_id": str(event.actor_user_id),
            "subject_generation": subject["generation"],
            "original_sent_at": event.original_sent_at,
            "edited_at": event.edited_at,
            "content_hash": digest,
            "source_kind": event.source_kind,
            "deleted": False,
            "ambiguous": ambiguous,
            "retained_evidence": bool(old.get("retained_evidence", False)),
        }
        if not item["retained_evidence"]:
            item["ttl"] = event.original_sent_at + RAW_RETENTION_SECONDS
        changed_subject = {**subject, "revision": int(subject["revision"]) + 1}
        self._transaction(
            [self._check_snapshot(control), self._put_cas(changed_subject, subject), self._put_cas(item, old)]
        )
        if ambiguous:
            raise MemorySourceConflict("Same-time edit was invalidated as ambiguous")
        return SourceRef(str(event.message_id), version, control["epoch"])

    def _observation_snapshot(self, chat_id, ref, *, learning=True):
        control = self._active_control(chat_id, learning=learning)
        observation = self.get_observation(chat_id, ref.source_id)
        if (
            not observation
            or observation["deleted"]
            or observation.get("ambiguous")
            or observation["epoch"] != ref.epoch
            or control["epoch"] != ref.epoch
            or observation["revision"] != ref.source_version
        ):
            raise MemoryUnavailable("Observation is missing or obsolete")
        subject = self._active_subject(chat_id, observation["actor_user_id"], control)
        if observation["subject_generation"] != subject["generation"]:
            raise MemoryUnavailable("Observation subject was deleted")
        return control, subject, observation

    def _coverage_operation(self, chat_id, outcome, *, amount=1):
        # Fixed, body-free counters. State CAS in the same transaction makes replay idempotent.
        from datetime import datetime, timezone

        if outcome not in {"accepted", "rejected", "candidate_expired", "work_done", "work_expired", "work_failed"}:
            raise MemoryInputError("Unsupported coverage outcome")
        day = datetime.fromtimestamp(self.now(), timezone.utc).strftime("%Y-%m-%d")
        return {
            "Update": {
                "TableName": self.table.name,
                "Key": {"pk": chat_key(chat_id), "sk": f"COVERAGE#{day}"},
                "UpdateExpression": "SET #ttl = :ttl ADD #metric :amount",
                "ExpressionAttributeNames": {"#metric": outcome, "#ttl": "ttl"},
                "ExpressionAttributeValues": {":amount": amount, ":ttl": self.now() + 90 * 86400},
            }
        }

    def prepare_candidate(self, event: SourceEvent, moderation_input_hash: str) -> SourceRef:
        import re

        from .safety import require_public_content

        ref = self.observe(event)
        event.validate()
        require_public_content(event.text, max_length=20000)
        if not isinstance(moderation_input_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", moderation_input_hash):
            raise MemoryInputError("Expected moderation input hash")
        control, subject, observation = self._observation_snapshot(event.chat_id, ref)
        key = f"ADMISSION#{ref.source_id}#{ref.source_version}"
        old = self._read(event.chat_id, key)
        if old:
            if old.get("moderation_input_hash") != moderation_input_hash:
                raise MemoryConflict("Moderation input changed for one source revision")
            return ref
        now = self.now()
        expires_at = min(now + CANDIDATE_RETENTION_SECONDS, event.original_sent_at + RAW_RETENTION_SECONDS)
        if expires_at <= now:
            raise MemoryUnavailable("Candidate source expired")
        admission = {
            "pk": chat_key(event.chat_id),
            "sk": key,
            "kind": "ADMISSION",
            "revision": 1,
            "source_ref": ref.as_dict(),
            "actor_user_id": str(event.actor_user_id),
            "subject_generation": subject["generation"],
            "state": "PENDING_REVIEW",
            "moderation_input_hash": moderation_input_hash,
            "content_hash": observation["content_hash"],
            "expires_at": expires_at,
            "created_at": now,
            "ttl": expires_at + WORK_RETENTION_SECONDS,
        }
        candidate = {
            "pk": chat_key(event.chat_id),
            "sk": f"CANDIDATE#{ref.source_id}#{ref.source_version}",
            "text": event.text,
            "quoted_spans": [list(span) for span in event.quoted_spans],
            "source_kind": event.source_kind,
            "source_ref": ref.as_dict(),
            "expires_at": expires_at,
            "ttl": expires_at,
        }
        self._transaction(
            [
                self._check_snapshot(control),
                self._check_snapshot(subject),
                self._check_snapshot(observation),
                self._put_cas(admission, {}),
                {"Put": {"TableName": self.table.name, "Item": candidate}},
            ]
        )
        return ref

    def _accept_operations(self, chat_id, ref, control, subject, observation, text, quoted_spans):
        from .safety import require_public_content

        require_public_content(text, max_length=20000)
        if source_hash(text, quoted_spans, observation["source_kind"]) != observation["content_hash"]:
            raise MemoryUnavailable("Canonical source hash mismatch")
        now = self.now()
        expires_at = int(observation["original_sent_at"]) + RAW_RETENTION_SECONDS
        if expires_at <= now:
            raise MemoryUnavailable("Accepted source is expired")
        old = self.get_source_head(chat_id, ref.source_id)
        if old and old["epoch"] == ref.epoch and old["revision"] == ref.source_version:
            return None
        common = {
            "pk": chat_key(chat_id),
            "source_id": ref.source_id,
            "revision": ref.source_version,
            "epoch": ref.epoch,
            "actor_user_id": observation["actor_user_id"],
            "subject_generation": subject["generation"],
            "original_sent_at": observation["original_sent_at"],
            "edited_at": observation["edited_at"],
            "content_hash": observation["content_hash"],
            "expires_at": expires_at,
            "source_kind": observation["source_kind"],
        }
        head = {
            **common,
            "sk": f"HEAD#{ref.source_id}",
            "deleted": False,
            "retained_evidence": bool(old.get("retained_evidence", False)),
        }
        if not head["retained_evidence"]:
            head["ttl"] = expires_at
        raw = {**common, "sk": f"RAW#{ref.source_id}", "text": text, "quoted_spans": quoted_spans, "ttl": expires_at}
        work = {
            "pk": chat_key(chat_id),
            "sk": self.work_key(ref),
            "kind": "WORK",
            "revision": 1,
            "source_ref": ref.as_dict(),
            "actor_user_id": observation["actor_user_id"],
            "source_kind": observation["source_kind"],
            "subject_generation": subject["generation"],
            "state": "PENDING",
            "lease_token": "",
            "lease_until": 0,
            "attempts": 0,
            "next_attempt_at": now,
            "due_at": now,
            "work_queue": work_queue(chat_id),
            "created_at": now,
            "original_sent_at": observation["original_sent_at"],
            "expires_at": expires_at,
            "ttl": expires_at + WORK_RETENTION_SECONDS,
        }
        if observation["source_kind"] == "confirmation":
            # Admin confirmation uses the explicit FactWriter lane, never a model.
            work.pop("work_queue")
            work.pop("due_at")
        return [
            self._check_snapshot(control),
            self._put_cas({**subject, "revision": int(subject["revision"]) + 1}, subject),
            self._check_snapshot(observation),
            self._put_cas(head, old),
            {"Put": {"TableName": self.table.name, "Item": raw}},
            self._put_cas(work, {}),
            self._coverage_operation(chat_id, "accepted"),
        ]

    def register_source(self, event: SourceEvent, *, expected_source_version=0) -> SourceRef:
        """Trusted deterministic CLEAN lane only; pending AI review uses promotion."""
        event.validate()
        integer(expected_source_version)
        old = self.get_source_head(event.chat_id, event.message_id)
        ref = self.observe(event)
        control, subject, observation = self._observation_snapshot(
            event.chat_id, ref, learning=event.source_kind == "message"
        )
        if old and old["revision"] == ref.source_version and old["epoch"] == ref.epoch:
            return ref
        if int(old.get("revision", 0)) != expected_source_version:
            raise MemoryConflict("Unexpected accepted source revision")
        operations = self._accept_operations(
            event.chat_id, ref, control, subject, observation, event.text, [list(span) for span in event.quoted_spans]
        )
        if operations:
            self._transaction(operations)
        return ref

    def promote_candidate(self, chat_id, ref: SourceRef, *, receipt_condition: dict, receipt_case_id: str):
        """Internal ingestion adapter entry: its trusted ModRepo owns the receipt table/schema."""
        control, subject, observation = self._observation_snapshot(chat_id, ref, learning=False)
        admission = self._read(chat_id, f"ADMISSION#{ref.source_id}#{ref.source_version}")
        if not admission:
            raise MemoryUnavailable("Candidate admission is missing")
        if admission["state"] == "ACCEPTED":
            return ref
        candidate = self._read(chat_id, f"CANDIDATE#{ref.source_id}#{ref.source_version}")
        if (
            admission["state"] != "PENDING_REVIEW"
            or not candidate
            or admission["expires_at"] <= self.now()
            or candidate["expires_at"] <= self.now()
        ):
            raise MemoryUnavailable("Candidate expired before approval")
        if not control["learning_enabled"]:
            raise MemoryLearningPaused("Candidate learning is temporarily paused")
        operations = self._accept_operations(
            chat_id, ref, control, subject, observation, candidate["text"], candidate["quoted_spans"]
        )
        if operations is None:
            # A deterministic safe adapter accepted the same source before its receipt arrived.
            operations = [
                self._check_snapshot(control),
                self._check_snapshot(subject),
                self._check_snapshot(observation),
            ]
        accepted = {
            **admission,
            "state": "ACCEPTED",
            "revision": int(admission["revision"]) + 1,
            "completed_at": self.now(),
            "receipt_case_id": receipt_case_id,
        }
        accepted.pop("ttl", None)  # Receipt ACK, not time, retires this durable outbox proof.
        now = self.now()
        if int(admission["expires_at"]) <= now or int(candidate["expires_at"]) <= now:
            raise MemoryUnavailable("Candidate expired during promotion")
        accepted_operation = self._put_cas(accepted, admission)
        accepted_operation["Put"]["ConditionExpression"] += " AND expires_at > :now AND #state = :pending"
        accepted_operation["Put"]["ExpressionAttributeNames"]["#state"] = "state"
        accepted_operation["Put"]["ExpressionAttributeValues"].update({":now": now, ":pending": "PENDING_REVIEW"})
        operations.extend(
            [
                receipt_condition,
                accepted_operation,
                {
                    "Delete": {
                        "TableName": self.table.name,
                        "Key": {"pk": candidate["pk"], "sk": candidate["sk"]},
                        "ConditionExpression": "expires_at > :now AND source_ref = :ref",
                        "ExpressionAttributeValues": {":now": now, ":ref": ref.as_dict()},
                    }
                },
            ]
        )
        self._transaction(operations)
        return ref

    def source_snapshot(self, chat_id, ref: SourceRef, *, learning=True):
        control, subject, observation = self._observation_snapshot(chat_id, ref, learning=learning)
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
        if head["content_hash"] != observation["content_hash"] or head["content_hash"] != source_hash(
            raw["text"], raw["quoted_spans"], raw["source_kind"]
        ):
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
            observation = self.get_observation(chat_id, ref["source_id"])
            if (
                not observation
                or observation.get("deleted")
                or observation.get("ambiguous")
                or not observation.get("retained_evidence")
                or observation.get("epoch") != ref["epoch"]
                or observation.get("revision") != ref["source_version"]
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

    def finish_admission(self, chat_id, ref, *, outcome):
        if outcome not in {"EXPIRED", "REJECTED"}:
            raise MemoryInputError("Unsupported admission terminal outcome")
        key = f"ADMISSION#{ref.source_id}#{ref.source_version}"
        old = self._read(chat_id, key)
        if old and old["state"] != "PENDING_REVIEW":
            return old["state"]
        item = {
            **old,
            "pk": chat_key(chat_id),
            "sk": key,
            "kind": "ADMISSION",
            "source_ref": ref.as_dict(),
            "revision": int(old.get("revision", 0)) + 1,
            "state": outcome,
            "completed_at": self.now(),
            "ttl": self.now() + WORK_RETENTION_SECONDS,
        }
        self._transaction(
            [
                self._put_cas(item, old),
                self._coverage_operation(chat_id, "rejected" if outcome == "REJECTED" else "candidate_expired"),
                {
                    "Delete": {
                        "TableName": self.table.name,
                        "Key": {"pk": chat_key(chat_id), "sk": f"CANDIDATE#{ref.source_id}#{ref.source_version}"},
                    }
                },
            ]
        )
        return outcome

    def claim_work(self, chat_id, ref: SourceRef) -> WorkLease | None:
        work = self.get_work(chat_id, ref)
        now = self.now()
        if not work or work["state"] in {"DONE", "EXPIRED", "FAILED"}:
            return None
        if work.get("source_kind") == "confirmation":
            return None
        if int(work["due_at"]) > now:
            return None
        if int(work["expires_at"]) <= now:
            self.finish_work(chat_id, ref, outcome="EXPIRED", reason="source_expired")
            return None
        try:
            control, subject, head, _ = self.source_snapshot(chat_id, ref, learning=False)
        except MemoryUnavailable:
            self.finish_work(chat_id, ref, outcome="EXPIRED", reason="source_revoked")
            return None
        if not control["learning_enabled"]:
            updated = {
                **work,
                "revision": int(work["revision"]) + 1,
                "state": "PENDING",
                "lease_token": "",
                "lease_until": 0,
                "next_attempt_at": now + 300,
                "due_at": now + 300,
                "last_reason": "learning_paused",
            }
            self._transaction([self._check_snapshot(control), self._put_cas(updated, work)])
            return None
        observation = self.get_observation(chat_id, ref.source_id)
        token = uuid.uuid4().hex
        until = now + WORK_LEASE_SECONDS
        updated = {
            **work,
            "revision": int(work["revision"]) + 1,
            "state": "LEASED",
            "lease_token": token,
            "lease_until": until,
            "due_at": until,
            "attempts": int(work["attempts"]) + 1,
            "first_attempt_at": work.get("first_attempt_at", now),
        }
        self._transaction(
            [
                self._check_snapshot(control),
                self._check_snapshot(subject),
                self._check_snapshot(head),
                self._check_snapshot(observation),
                self._put_cas(updated, work),
            ]
        )
        return WorkLease(ref, token, int(subject["generation"]), until)

    def valid_leased_source(self, chat_id, lease: WorkLease) -> ExtractionSource:
        _, subject, head, raw = self.source_snapshot(chat_id, lease.source_ref)
        work = self.get_work(chat_id, lease.source_ref)
        now = self.now()
        if (
            not work
            or work["state"] != "LEASED"
            or work["lease_token"] != lease.token
            or work["lease_until"] != lease.lease_until
            or int(work["lease_until"]) <= now
            or int(work["expires_at"]) <= now
            or subject["generation"] != lease.subject_generation
        ):
            raise MemoryUnavailable("Extraction lease is missing, expired or revoked")
        return ExtractionSource(
            str(chat_id),
            lease.source_ref,
            head["actor_user_id"],
            raw["text"],
            tuple((int(a), int(b)) for a, b in raw["quoted_spans"]),
            int(head["original_sent_at"]),
            int(head["edited_at"]),
        )

    def retry_work(self, chat_id, lease, *, retry_at, reason="retry"):
        work = self.get_work(chat_id, lease.source_ref)
        if not work or work["state"] != "LEASED" or work["lease_token"] != lease.token:
            return False
        now = self.now()
        if int(work["expires_at"]) <= now:
            return self.finish_work(chat_id, lease.source_ref, outcome="EXPIRED", reason="source_expired", lease=lease)
        due = min(int(work["expires_at"]), max(now + 1, int(retry_at)))
        # Do not persist provider strings: callers map errors to this bounded vocabulary.
        if reason not in {"retry", "provider", "budget", "quota", "schema", "batch_input_limit", "conflict", "paused"}:
            reason = "retry"
        updated = {
            **work,
            "state": "PENDING",
            "revision": int(work["revision"]) + 1,
            "lease_token": "",
            "lease_until": 0,
            "next_attempt_at": due,
            "due_at": due,
            "last_reason": reason,
        }
        self._transaction([self._put_cas(updated, work)])
        return True

    def finish_work(self, chat_id, ref, *, outcome, reason, lease=None):
        if outcome not in {"EXPIRED", "FAILED"}:
            raise MemoryInputError("Unsupported work terminal state")
        if reason not in {"source_expired", "source_revoked", "input_limit", "invalid_source"}:
            raise MemoryInputError("Unsupported work failure reason")
        work = self.get_work(chat_id, ref)
        if not work or work["state"] in {"DONE", "EXPIRED", "FAILED"}:
            return False
        if lease and (work["state"] != "LEASED" or work["lease_token"] != lease.token):
            return False
        updated = {
            **work,
            "state": outcome,
            "revision": int(work["revision"]) + 1,
            "last_reason": reason,
            "completed_at": self.now(),
            "ttl": self.now() + WORK_RETENTION_SECONDS,
        }
        updated.pop("work_queue", None)
        updated.pop("due_at", None)
        self._transaction(
            [
                self._put_cas(updated, work),
                self._coverage_operation(chat_id, "work_expired" if outcome == "EXPIRED" else "work_failed"),
            ]
        )
        return True

    def list_due_work(self, shard, *, limit=100, cursor=None):
        integer(shard)
        if shard >= WORK_SHARDS:
            raise MemoryInputError("Unknown work shard")
        args = {
            "IndexName": WORK_INDEX_NAME,
            "KeyConditionExpression": Key("work_queue").eq(f"MEMORY_WORK#{shard}") & Key("due_at").lte(self.now()),
            "Limit": max(1, min(100, limit)),
        }
        if cursor:
            args["ExclusiveStartKey"] = cursor
        page = self.table.query(**args)
        rows = []
        for candidate in page.get("Items", []):
            # GSI entries are hints. Only the strongly read base row owns work state.
            row = self.table.get_item(Key={"pk": candidate["pk"], "sk": candidate["sk"]}, ConsistentRead=True).get(
                "Item"
            )
            if row and row.get("state") in {"PENDING", "LEASED"} and row.get("due_at", self.now() + 1) <= self.now():
                rows.append(row)
        return rows, page.get("LastEvaluatedKey")

    def list_pending_admissions(self, *, limit=100, cursor=None):
        args = {
            "FilterExpression": Attr("kind").eq("ADMISSION")
            & (Attr("state").eq("PENDING_REVIEW") | (Attr("state").eq("ACCEPTED") & Attr("ttl").not_exists())),
            "ConsistentRead": True,
            "Limit": max(1, min(100, limit)),
        }
        if cursor:
            args["ExclusiveStartKey"] = cursor
        page = self.table.scan(**args)
        return page.get("Items", []), page.get("LastEvaluatedKey")

    def complete_admission_ack(self, chat_id, ref):
        admission = self._read(chat_id, f"ADMISSION#{ref.source_id}#{ref.source_version}")
        if not admission or admission["state"] != "ACCEPTED" or "ttl" in admission:
            return
        self._transaction(
            [
                self._put_cas(
                    {
                        **admission,
                        "revision": int(admission["revision"]) + 1,
                        "ttl": self.now() + WORK_RETENTION_SECONDS,
                    },
                    admission,
                )
            ]
        )

    def recovery_checkpoint(self, name):
        if name not in {"admissions", "clean", "work0", "work1", "work2", "work3"}:
            raise MemoryInputError("Unknown recovery cursor")
        return self.table.get_item(Key={"pk": "RECOVERY", "sk": name}, ConsistentRead=True).get("Item") or {}

    def save_recovery_checkpoint(self, name, previous, cursor):
        item = {
            "pk": "RECOVERY",
            "sk": name,
            "revision": int(previous.get("revision", 0)) + 1,
            "cursor": cursor or {},
            "updated_at": self.now(),
        }
        self._transaction([self._put_cas(item, previous)])

    def coverage_snapshot(self, chat_id):
        """Body-free observed outcomes, not a claim of product acceptance or perfect recall."""
        now = self.now()
        counts = {"pending": 0, "leased": 0, "paused": 0, "done": 0, "expired": 0, "failed": 0}
        ages, latencies, recovered_latencies = [], [], []
        for row in self._list(chat_id, "WORK#"):
            state = row.get("state", "").lower()
            if state in counts:
                counts[state] += 1
            if state in {"pending", "leased"}:
                ages.append(max(0, now - int(row.get("created_at", now))))
                if row.get("last_reason") in {"budget", "quota", "paused", "learning_paused"}:
                    counts["paused"] += 1
            if state == "done":
                elapsed = max(0, int(row["completed_at"]) - int(row.get("original_sent_at", row["completed_at"])))
                (recovered_latencies if "first_recovery_at" in row else latencies).append(elapsed)

        def p95(values):
            import math

            return sorted(values)[max(0, math.ceil(len(values) * 0.95) - 1)] if values else None

        counters = {}
        for row in self._list(chat_id, "COVERAGE#"):
            if int(row.get("ttl", 0)) <= now:
                continue
            for metric in ("accepted", "rejected", "candidate_expired", "work_done", "work_expired", "work_failed"):
                counters[metric] = counters.get(metric, 0) + int(row.get(metric, 0))
        return {
            **counts,
            "pending_oldest_seconds": max(ages, default=0),
            "normal_completed_samples": len(latencies),
            "normal_p95_seconds": p95(latencies),
            "recovery_completed_samples": len(recovered_latencies),
            "recovery_p95_seconds": p95(recovered_latencies),
            "outcomes": counters,
        }

    def note_recovery(self, chat_id, ref):
        work = self.get_work(chat_id, ref)
        if not work or work["state"] not in {"PENDING", "LEASED"} or "first_recovery_at" in work:
            return
        self._transaction(
            [self._put_cas({**work, "revision": int(work["revision"]) + 1, "first_recovery_at": self.now()}, work)]
        )
