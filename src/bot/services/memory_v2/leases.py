"""Bounded, body-free answer leases shared by answering and deletion."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, chat_key, positive_id

ANSWER_LEASE_SECONDS = 360
MAX_ANSWER_SUBJECTS = 8
MAX_ANSWER_FACTS = 16


def _subjects(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= MAX_ANSWER_SUBJECTS:
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
        return [self.repo._check_snapshot(row) for row in unique.values()]

    def acquire(self, chat_id, subject_ids, *, request_id):
        chat_key(chat_id)
        names = _subjects(subject_ids)
        if not isinstance(request_id, str) or not request_id or len(request_id) > 256:
            raise MemoryInputError("An answer request identity is required")
        control = self.repo._active_control(chat_id)
        subjects = [self.repo._active_subject(chat_id, name, control) for name in names]
        now = self.repo.now()
        row = {
            "pk": chat_key(chat_id),
            "sk": "ANSWER_LEASE#" + hashlib.sha256(request_id.encode()).hexdigest(),
            "kind": "ANSWER_LEASE",
            "revision": 1,
            "token": uuid.uuid4().hex,
            "state": "ACTIVE",
            "epoch": control["epoch"],
            "control_revision": control["revision"],
            "subject_ids": list(names),
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
        self.repo._transaction([*self._checks([control, *subjects]), self.repo._put_cas(row, {})])
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
            or int(row["lease_until"]) <= self.repo.now()
        ):
            raise MemoryUnavailable("Answer lease is expired, released or replaced")
        control = self.repo._active_control(lease.chat_id)
        if control["epoch"] != row["epoch"] or control["revision"] != row["control_revision"]:
            raise MemoryUnavailable("Answer control changed")
        subjects = []
        for name, expected in row["subjects"].items():
            subject = self.repo._active_subject(lease.chat_id, name, control)
            if subject["revision"] != expected["revision"] or subject["generation"] != expected["generation"]:
                raise MemoryUnavailable("Answer subject changed")
            subjects.append(subject)
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

    def bind(self, lease, fact_refs):
        refs = fact_references(fact_refs)
        row, control, subjects = self._live(lease)
        if row["bound"]:
            if row["fact_refs"] != refs:
                raise MemoryConflict("An answer lease cannot change its selected facts")
            self.validate(lease, refs)
            return lease
        fences, authors, sources = [control, *subjects], set(), []
        for ref in refs:
            checked = self._fact(lease, ref, control)
            fences.extend(checked)
            authors.add(checked[3]["actor_user_id"])
            sources.append(checked[0]["evidence"]["source_ref"])
        updated = {
            **row,
            "revision": int(row["revision"]) + 1,
            "bound": True,
            "fact_refs": refs,
            "source_refs": sources,
            "evidence_authors": sorted(authors),
        }
        operation = self.repo._put_cas(updated, row)
        operation["Put"]["ConditionExpression"] += " AND lease_until > :now AND #token = :token"
        operation["Put"]["ExpressionAttributeNames"]["#token"] = "token"
        operation["Put"]["ExpressionAttributeValues"].update({":now": self.repo.now(), ":token": lease.token})
        self.repo._transaction([*self._checks(fences), operation])
        if self.repo.now() >= lease.lease_until:
            raise MemoryUnavailable("Answer binding expired during commit")
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
        self.repo._transaction([*self._checks(fences), self._lease_check(row)])
        if self.repo.now() + 40 >= lease.lease_until:
            raise MemoryUnavailable("Insufficient answer lease time after validation")

    def release(self, lease):
        if not isinstance(lease, AnswerLease):
            raise MemoryInputError("Expected an answer lease")
        row = self.repo._read(lease.chat_id, lease.lease_id)
        if not row or row.get("token") != lease.token or row.get("state") == "RELEASED":
            return
        updated = {**row, "revision": int(row["revision"]) + 1, "state": "RELEASED", "released_at": self.repo.now()}
        self.repo._transaction([self.repo._put_cas(updated, row)])
