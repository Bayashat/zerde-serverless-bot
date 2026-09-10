"""Bounded, body-free answer leases shared by answering and deletion."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, SourceRef, chat_key, positive_id

ANSWER_LEASE_SECONDS = 360
MAX_ANSWER_SUBJECTS = 8
MAX_ANSWER_FACTS = 16
MAX_EXTRA_SOURCES = 10
EXTRA_SOURCE_WINDOWS = {"trend": 7 * 86400, "media": 86400}


def _subjects(values, *, allow_empty=False):
    if not isinstance(values, (list, tuple)) or not (0 if allow_empty else 1) <= len(values) <= MAX_ANSWER_SUBJECTS:
        raise MemoryInputError("An answer requires one to eight scoped subjects")
    names = tuple("GROUP" if value == "GROUP" else positive_id(value) for value in values)
    if len(set(names)) != len(names):
        raise MemoryInputError("Duplicate answer subject")
    return tuple(sorted(names))


def fact_references(values):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ANSWER_FACTS:
        raise MemoryInputError("Too many answer fact references")
    refs = []
    for value in values:
        if (
            not isinstance(value, dict)
            or set(value) != {"fact_id", "fact_version"}
            or not isinstance(value["fact_id"], str)
            or not value["fact_id"].startswith("FACT#")
            or len(value["fact_id"]) > 240
            or type(value["fact_version"]) is not int
            or value["fact_version"] < 1
        ):
            raise MemoryInputError("Invalid answer fact reference")
        refs.append(dict(value))
    if len({ref["fact_id"] for ref in refs}) != len(refs):
        raise MemoryInputError("Duplicate answer fact reference")
    return sorted(refs, key=lambda ref: ref["fact_id"])


def extra_source_references(values, kind):
    if not isinstance(kind, str) or kind not in EXTRA_SOURCE_WINDOWS:
        raise MemoryInputError("Unsupported extra source class")
    if not isinstance(values, (list, tuple)) or len(values) > MAX_EXTRA_SOURCES:
        raise MemoryInputError("Too many extra answer sources")
    if any(not isinstance(ref, SourceRef) for ref in values):
        raise MemoryInputError("Expected typed extra source references")
    if len({ref.source_id for ref in values}) != len(values):
        raise MemoryInputError("Duplicate extra answer source")
    return sorted(values, key=lambda ref: int(ref.source_id))


@dataclass(frozen=True)
class AnswerLease:
    chat_id: str
    lease_id: str
    token: str
    revision: int
    epoch: str
    lease_until: int
    subject_ids: tuple[str, ...]
    bound: bool = False
    actor_user_id: str | None = None


class AnswerLeaseService:
    def __init__(self, repo):
        self.repo = repo

    @staticmethod
    def _view(row):
        return AnswerLease(
            row["pk"].removeprefix("CHAT#"),
            row["sk"],
            row["token"],
            int(row["revision"]),
            row["epoch"],
            int(row["lease_until"]),
            tuple(row["subject_ids"]),
            bool(row["bound"]),
            row.get("actor_user_id"),
        )

    def _checks(self, rows):
        unique = {}
        for row in rows:
            key = row["pk"], row["sk"]
            if key in unique and unique[key]["revision"] != row["revision"]:
                raise MemoryConflict("Answer snapshots changed during lookup")
            unique[key] = row
        if len(unique) > 98:
            raise MemoryInputError("Answer snapshot exceeds the atomic fence limit")
        return [
            (
                {
                    "ConditionCheck": {
                        "TableName": self.repo.table.name,
                        "Key": {"pk": row["pk"], "sk": row["sk"]},
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                }
                if row.get("_lease_absent")
                else self.repo._check_snapshot(row)
            )
            for row in unique.values()
        ]

    def _actor_snapshot(self, chat_id, actor):
        if actor is None:
            return None
        row = self.repo.get_subject(chat_id, actor)
        if row:
            # Opt-out disables learning/profile selection, not asking about other people.
            # An old-epoch actor row is metadata only; current facts still need _active_subject.
            if row.get("state") != "ACTIVE":
                raise MemoryUnavailable("Answer requester is being erased")
            return row
        return {"pk": chat_key(chat_id), "sk": self.repo.subject_key(actor), "revision": None, "_lease_absent": True}

    def retry_unsent(self, chat_id, request_id):
        """Only reclaim a dead lease before any durable delivery was prepared."""
        digest = hashlib.sha256(request_id.encode()).hexdigest()
        row = self.repo._read(chat_id, "ANSWER_LEASE#" + digest)
        if not row or (row.get("state") == "ACTIVE" and int(row["lease_until"]) > self.repo.now()):
            return
        receipt_key = {"pk": row["pk"], "sk": "ANSWER_REQUEST#" + digest}
        if self.repo._read(chat_id, receipt_key["sk"]):
            return
        self.repo._transaction(
            [
                {
                    "ConditionCheck": {
                        "TableName": self.repo.table.name,
                        "Key": receipt_key,
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                {
                    "Delete": {
                        "TableName": self.repo.table.name,
                        "Key": {"pk": row["pk"], "sk": row["sk"]},
                        "ConditionExpression": "#revision = :revision",
                        "ExpressionAttributeNames": {"#revision": "revision"},
                        "ExpressionAttributeValues": {":revision": row["revision"]},
                    }
                },
            ]
        )

    def _control(self, chat_id, *, plain=False):
        if not plain:
            return self.repo._active_control(chat_id)
        control = self.repo.get_control(chat_id)
        if control.get("state") not in {"ACTIVE", "STOPPED"}:
            raise MemoryUnavailable("Explicit answer overlaps group erasure")
        # A never-activated group still needs durable, body-free send deduplication.
        return {**control, "_lease_absent": True} if control["revision"] == 0 else control

    def acquire(self, chat_id, subject_ids, *, request_id, actor_user_id=None, plain=False):
        chat_key(chat_id)
        actor = positive_id(actor_user_id) if actor_user_id is not None else None
        names = _subjects(subject_ids, allow_empty=actor is not None)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise MemoryInputError("An answer request identity is required")
        if plain and (names or actor is None):
            raise MemoryInputError("Plain delivery cannot select memory subjects")
        control = self._control(chat_id, plain=plain)
        subjects = [self.repo._active_subject(chat_id, name, control) for name in names]
        actor_snapshot = self._actor_snapshot(chat_id, actor)
        now = self.repo.now()
        row = {
            "pk": chat_key(chat_id),
            "sk": "ANSWER_LEASE#" + hashlib.sha256(request_id.encode()).hexdigest(),
            "kind": "ANSWER_LEASE",
            "plain": plain,
            "revision": 1,
            "token": uuid.uuid4().hex,
            "state": "ACTIVE",
            "epoch": control["epoch"],
            "control_revision": control["revision"],
            "subject_ids": list(names),
            "actor_user_id": actor,
            "actor_subject_revision": actor_snapshot["revision"] if actor_snapshot else None,
            "subjects": {
                name: {"revision": subject["revision"], "generation": subject["generation"]}
                for name, subject in zip(names, subjects)
            },
            "bound": False,
            "fact_refs": [],
            "source_refs": [],
            "evidence_authors": [],
            "created_at": now,
            "lease_until": now + ANSWER_LEASE_SECONDS,
            "ttl": now + 7 * 86400,
        }
        self.repo._transaction(
            [
                *self._checks([control, *subjects, *([actor_snapshot] if actor_snapshot else [])]),
                self.repo._put_cas(row, {}),
            ]
        )
        return self._view(row)

    def _live(self, lease):
        if not isinstance(lease, AnswerLease):
            raise MemoryInputError("Expected an answer lease")
        row = self.repo._read(lease.chat_id, lease.lease_id)
        if (
            not row
            or row.get("kind") != "ANSWER_LEASE"
            or row.get("state") != "ACTIVE"
            or row.get("token") != lease.token
            or row.get("revision") != lease.revision
            or row.get("epoch") != lease.epoch
            or row.get("lease_until") != lease.lease_until
            or tuple(row.get("subject_ids", ())) != lease.subject_ids
            or row.get("bound") != lease.bound
            or row.get("actor_user_id") != lease.actor_user_id
            or int(row["lease_until"]) <= self.repo.now()
        ):
            raise MemoryUnavailable("Answer lease is expired, released or replaced")
        control = self._control(lease.chat_id, plain=row.get("plain", False))
        if control["epoch"] != row["epoch"] or control["revision"] != row["control_revision"]:
            raise MemoryUnavailable("Answer control changed")
        subjects = []
        for name, expected in row["subjects"].items():
            subject = self.repo._active_subject(lease.chat_id, name, control)
            if subject["revision"] != expected["revision"] or subject["generation"] != expected["generation"]:
                raise MemoryUnavailable("Answer subject changed")
            subjects.append(subject)
        actor_snapshot = self._actor_snapshot(lease.chat_id, lease.actor_user_id)
        if actor_snapshot:
            if actor_snapshot["revision"] != row.get("actor_subject_revision"):
                raise MemoryUnavailable("Answer requester metadata changed")
            subjects.append(actor_snapshot)
        return row, control, subjects

    def _fact(self, lease, ref, control):
        fact = self.repo._read(lease.chat_id, ref["fact_id"])
        names = {"GROUP" if name == "GROUP" else "USER#" + name for name in lease.subject_ids}
        if (
            not fact
            or fact.get("status") != "ACTIVE"
            or fact.get("fact_version") != ref["fact_version"]
            or fact.get("revision") != ref["fact_version"]
            or fact.get("epoch") != lease.epoch
            or fact.get("subject_id") not in names
            or int(fact.get("valid_from", self.repo.now() + 1)) > self.repo.now()
        ):
            raise MemoryUnavailable("Answer fact is no longer current")
        name = fact["subject_id"].removeprefix("USER#")
        subject = self.repo._active_subject(lease.chat_id, name, control)
        if subject["generation"] != fact["subject_generation"]:
            raise MemoryUnavailable("Answer fact subject was erased")
        source_ref = fact["evidence"]["source_ref"]
        head = self.repo.get_source_head(lease.chat_id, source_ref["source_id"])
        observation = self.repo.get_observation(lease.chat_id, source_ref["source_id"])
        for pointer in (head, observation):
            if (
                not pointer
                or pointer.get("deleted")
                or pointer.get("ambiguous")
                or not pointer.get("retained_evidence")
                or pointer.get("epoch") != source_ref["epoch"]
                or pointer.get("revision") != source_ref["source_version"]
                or pointer.get("epoch") != lease.epoch
            ):
                raise MemoryUnavailable("Answer evidence was edited or erased")
        author = self.repo._active_subject(lease.chat_id, head["actor_user_id"], control)
        if (
            author["generation"] != head["subject_generation"]
            or head["actor_user_id"] != fact["evidence"]["actor_user_id"]
            or observation["actor_user_id"] != head["actor_user_id"]
            or observation["subject_generation"] != author["generation"]
        ):
            raise MemoryUnavailable("Answer evidence author changed")
        return fact, subject, author, head, observation

    def _lease_check(self, row):
        operation = self.repo._check_snapshot(row)
        check = operation["ConditionCheck"]
        check["ConditionExpression"] += " AND #state = :active AND #token = :token AND lease_until > :now"
        check["ExpressionAttributeNames"]["#state"] = "state"
        check["ExpressionAttributeNames"]["#token"] = "token"
        check["ExpressionAttributeValues"].update(
            {":active": "ACTIVE", ":token": row["token"], ":now": self.repo.now()}
        )
        return operation

    def snapshot(self, lease):
        row, control, subjects = self._live(lease)
        facts, fences = [], [control, *subjects]
        # Profile reads have no raw-body dependency: retained minimal evidence remains
        # useful after RAW TTL, while source pointers and subject revisions still fence it.
        for name in lease.subject_ids:
            current = self.repo.get_profile(lease.chat_id, name)
            for fact in current:
                checked = self._fact(
                    lease, {"fact_id": fact["fact_id"], "fact_version": int(fact["fact_version"])}, control
                )
                if checked[0]["revision"] != fact["revision"]:
                    raise MemoryConflict("Answer fact changed while reading")
                facts.append(fact)
                # Every fact writer increments the target subject and every observation
                # edit increments its author. Those revisions fence this unbounded read.
                fences.extend(checked[1:3])
        if self.repo.now() >= lease.lease_until:
            raise MemoryUnavailable("Answer snapshot exceeded its lease")
        self.repo._transaction([*self._checks(fences), self._lease_check(row)])
        if self.repo.now() >= lease.lease_until:
            raise MemoryUnavailable("Answer snapshot expired during validation")
        return facts

    def _extra_source(self, lease, ref, kind):
        if ref.epoch != lease.epoch:
            raise MemoryUnavailable("Extra source belongs to an obsolete epoch")
        control, author, observation = self.repo._observation_snapshot(lease.chat_id, ref, learning=False)
        now = self.repo.now()
        original = int(observation["original_sent_at"])
        if (
            observation["source_kind"] != "message"
            or original < max(control["learning_started_at"], author["learning_started_at"])
            or original > now
            or observation["edited_at"] > now
        ):
            raise MemoryUnavailable("Extra source is outside its original scope")
        expires_at = original + EXTRA_SOURCE_WINDOWS[kind]
        fences = [control, author, observation]
        if kind == "trend":
            # A trend must still have its current accepted body. A media-only OBS
            # cannot be used as a shortcut around that requirement.
            source_control, source_author, head, raw = self.repo.source_snapshot(lease.chat_id, ref, learning=False)
            for pointer in (head, raw):
                if any(
                    pointer[key] != observation[key]
                    for key in ("actor_user_id", "subject_generation", "original_sent_at", "edited_at", "source_kind")
                ):
                    raise MemoryUnavailable("Extra source identity changed")
            expires_at = min(expires_at, int(head["expires_at"]), int(raw["expires_at"]), int(raw["ttl"]))
            fences.extend((source_control, source_author, head, raw))
        elif observation["edited_at"]:
            raise MemoryUnavailable("Edited media cannot reuse its original album reference")
        if expires_at <= now:
            raise MemoryUnavailable("Extra source window expired")
        scope = {
            "source_id": ref.source_id,
            "actor_user_id": observation["actor_user_id"],
            "subject_generation": author["generation"],
            "expires_at": expires_at,
        }
        return fences, scope

    def _bound_extra_sources(self, lease, row):
        values = row.get("extra_source_refs", [])
        kind = row.get("extra_source_kind")
        scopes = row.get("extra_source_scopes", [])
        if not values:
            if kind is not None or scopes:
                raise MemoryUnavailable("Extra source binding is inconsistent")
            return [], []
        try:
            refs = extra_source_references(
                [SourceRef(value["source_id"], int(value["source_version"]), value["epoch"]) for value in values], kind
            )
            if [ref.as_dict() for ref in refs] != values:
                raise MemoryInputError("Noncanonical extra source binding")
        except (KeyError, TypeError, ValueError) as exc:
            raise MemoryUnavailable("Extra source binding is invalid") from exc
        fences, current_scopes = [], []
        for ref in refs:
            checked, scope = self._extra_source(lease, ref, kind)
            fences.extend(checked)
            current_scopes.append(scope)
        if current_scopes != scopes:
            raise MemoryUnavailable("Extra source ownership or window changed")
        return fences, current_scopes

    def _extra_window(self, scopes, *, margin=0):
        if any(int(scope["expires_at"]) <= self.repo.now() + margin for scope in scopes):
            raise MemoryUnavailable("Insufficient extra source lifetime for this operation")

    def bind(self, lease, fact_refs, *, extra_source_refs=(), extra_source_kind="trend"):
        """Bind facts plus optional typed sources to one immutable source class.

        Only trusted service code chooses the class: trend callers require RAW;
        media callers must first validate the actual ephemeral album references.
        This API does not authorize media, turn text into media, or change a bound
        lease's class. The classes never relax the retained-fact evidence path.
        """
        refs = fact_references(fact_refs)
        extra_refs = extra_source_references(extra_source_refs, extra_source_kind)
        extra_values = [ref.as_dict() for ref in extra_refs]
        extra_kind = extra_source_kind if extra_refs else None
        row, control, subjects = self._live(lease)
        if row.get("plain") and (refs or (extra_refs and control["state"] != "ACTIVE")):
            raise MemoryInputError("Inactive/plain delivery cannot bind retained facts")
        if row["bound"]:
            if (
                row["fact_refs"] != refs
                or row.get("extra_source_refs", []) != extra_values
                or row.get("extra_source_kind") != extra_kind
            ):
                raise MemoryConflict("An answer lease cannot change its selected references or class")
            self.validate(lease, refs)
            return lease
        fences, authors, sources = [control, *subjects], set(), []
        for ref in refs:
            checked = self._fact(lease, ref, control)
            fences.extend(checked)
            authors.add(checked[3]["actor_user_id"])
            sources.append(checked[0]["evidence"]["source_ref"])
        extra_scopes = []
        for ref in extra_refs:
            checked, scope = self._extra_source(lease, ref, extra_kind)
            fences.extend(checked)
            authors.add(scope["actor_user_id"])
            sources.append(ref.as_dict())
            extra_scopes.append(scope)
        unique_sources = {}
        for source in sources:
            if source["source_id"] in unique_sources and unique_sources[source["source_id"]] != source:
                raise MemoryConflict("Answer references mix source versions")
            unique_sources[source["source_id"]] = source
        updated = {
            **row,
            "revision": int(row["revision"]) + 1,
            "bound": True,
            "fact_refs": refs,
            "source_refs": [unique_sources[key] for key in sorted(unique_sources, key=int)],
            "evidence_authors": sorted(authors),
            "extra_source_kind": extra_kind,
            "extra_source_refs": extra_values,
            "extra_source_scopes": extra_scopes,
        }
        operation = self.repo._put_cas(updated, row)
        operation["Put"]["ConditionExpression"] += " AND lease_until > :now AND #token = :token"
        operation["Put"]["ExpressionAttributeNames"]["#token"] = "token"
        operation["Put"]["ExpressionAttributeValues"].update({":now": self.repo.now(), ":token": lease.token})
        self.repo._transaction([*self._checks(fences), operation])
        if self.repo.now() >= lease.lease_until:
            raise MemoryUnavailable("Answer binding expired during commit")
        self._extra_window(extra_scopes)
        return self._view(updated)

    def validate(self, lease, fact_refs):
        refs = fact_references(fact_refs)
        row, control, subjects = self._live(lease)
        if self.repo.now() + 40 >= lease.lease_until:
            raise MemoryUnavailable("Insufficient answer lease time for a bounded send")
        if not row["bound"] or row["fact_refs"] != refs:
            raise MemoryUnavailable("Answer references were not bound to this lease")
        fences = [control, *subjects]
        for ref in refs:
            fences.extend(self._fact(lease, ref, control))
        extra_fences, extra_scopes = self._bound_extra_sources(lease, row)
        fences.extend(extra_fences)
        self._extra_window(extra_scopes, margin=40)
        self.repo._transaction([*self._checks(fences), self._lease_check(row)])
        if self.repo.now() + 40 >= lease.lease_until:
            raise MemoryUnavailable("Insufficient answer lease time after validation")
        self._extra_window(extra_scopes, margin=40)

    def release(self, lease):
        if not isinstance(lease, AnswerLease):
            raise MemoryInputError("Expected an answer lease")
        row = self.repo._read(lease.chat_id, lease.lease_id)
        if not row or row.get("token") != lease.token or row.get("state") == "RELEASED":
            return
        updated = {**row, "revision": int(row["revision"]) + 1, "state": "RELEASED", "released_at": self.repo.now()}
        self.repo._transaction([self.repo._put_cas(updated, row)])
