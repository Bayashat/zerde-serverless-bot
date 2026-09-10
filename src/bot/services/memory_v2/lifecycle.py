"""Durable deletion coordinator over the single V2 table and registered owners."""

from __future__ import annotations

import time

from boto3.dynamodb.conditions import Attr, Key

from .leases import ANSWER_LEASE_SECONDS
from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, chat_key, positive_id


class MemoryPurgeRecoveryError(RuntimeError):
    """At least one durable purge remains pending after independent work progressed."""


class MemoryLifecycle:
    def __init__(self, repo, *, derived_cleaners=()):
        self.repo = repo
        self.derived_cleaners = tuple(derived_cleaners)

    def begin(self, chat_id, *, scope, target=None, optout=False):
        if scope not in {"group", "subject", "source"} or (optout and scope != "subject"):
            raise MemoryInputError("Unsupported memory deletion scope")
        target = "GROUP" if scope == "group" else positive_id(target)
        key = f"PURGE#{scope.upper()}#{target}"
        old = self.repo._read(chat_id, key)
        if old and old["state"] != "DONE":
            if optout and not old.get("optout"):
                control, subject = self._fence(chat_id, old)
                updated = {**old, "revision": int(old["revision"]) + 1, "optout": True}
                self.repo._transaction(
                    [
                        self.repo._check_snapshot(control),
                        self.repo._put_cas(
                            {**subject, "revision": int(subject["revision"]) + 1, "optout": True}, subject
                        ),
                        self.repo._put_cas(updated, old),
                    ]
                )
                return updated
            return old
        if any(row["state"] != "DONE" for row in self.repo._list(chat_id, "PURGE#")):
            raise MemoryConflict("Another scoped deletion is already in progress")
        control = self.repo._active_control(chat_id)
        now = self.repo.now()
        job = {
            "pk": chat_key(chat_id),
            "sk": key,
            "kind": "PURGE",
            "revision": int(old.get("revision", 0)) + 1,
            "state": "WAITING",
            "scope": scope,
            "target": target,
            "epoch": control["epoch"],
            "optout": bool(optout),
            "created_at": now,
            "cursor": {},
            "deleted_rows": 0,
        }
        if scope == "group":
            stopped = {
                **control,
                "state": "STOPPING",
                "learning_enabled": False,
                "revision": int(control["revision"]) + 1,
            }
            operations = [self.repo._put_cas(stopped, control)]
        elif scope == "subject":
            subject = self.repo._ensure_subject(chat_id, target, control)
            if subject["state"] != "ACTIVE":
                raise MemoryUnavailable("Subject deletion is already in progress")
            job["old_generation"] = subject["generation"]
            stopped = {
                **subject,
                "state": "STOPPING",
                "generation": int(subject["generation"]) + 1,
                "revision": int(subject["revision"]) + 1,
                "learning_started_at": now + 1,
                "optout": bool(optout or subject["optout"]),
            }
            operations = [
                self.repo._put_cas({**control, "revision": int(control["revision"]) + 1}, control),
                self.repo._put_cas(stopped, subject),
            ]
        else:
            observation = self.repo.get_observation(chat_id, target)
            if not observation or observation.get("deleted") or observation["epoch"] != control["epoch"]:
                raise MemoryUnavailable("Source is missing or already erased")
            author = self.repo._active_subject(chat_id, observation["actor_user_id"], control)
            job["actor_user_id"] = author["sk"].removeprefix("SUBJECT#USER#")
            job["source_version"] = observation["revision"]
            stopped = {**observation, "deleted": True, "revision": int(observation["revision"]) + 1}
            stopped.pop("ttl", None)
            operations = [
                self.repo._put_cas({**control, "revision": int(control["revision"]) + 1}, control),
                self.repo._put_cas(stopped, observation),
                self.repo._put_cas({**author, "revision": int(author["revision"]) + 1}, author),
            ]
        self.repo._transaction([*operations, self.repo._put_cas(job, old)])
        return job

    def _matching_lease(self, job, row):
        if row.get("kind") == "ANSWER_LEASE":
            if row.get("state") != "ACTIVE" or int(row.get("lease_until", 0)) <= self.repo.now():
                return False
            if job["scope"] == "group" or not row.get("bound"):
                return True
            if job["scope"] == "subject":
                return job["target"] in row.get("subject_ids", []) or job["target"] in row.get("evidence_authors", [])
            return any(ref.get("source_id") == job["target"] for ref in row.get("source_refs", []))
        if row.get("kind") == "WORK" and row.get("state") == "LEASED":
            return int(row.get("lease_until", 0)) > self.repo.now() and self._belongs(job, row)
        return False

    def _inflight(self, chat_id, job):
        # Every prior answer has a fixed <=360s lease and extraction <=130s.
        # begin() changes CONTROL revision, so a newly acquired answer cannot
        # bind a pre-deletion snapshot. This deadline bounds even a huge scan.
        if self.repo.now() >= int(job["created_at"]) + ANSWER_LEASE_SECONDS:
            return False
        for prefix in ("ANSWER_LEASE#", "WORK#"):
            cursor = None
            for _ in range(4):
                args = {
                    "KeyConditionExpression": Key("pk").eq(chat_key(chat_id)) & Key("sk").begins_with(prefix),
                    "ConsistentRead": True,
                    "Limit": 40,
                }
                if cursor:
                    args["ExclusiveStartKey"] = cursor
                page = self.repo.table.query(**args)
                if any(self._matching_lease(job, row) for row in page.get("Items", [])):
                    return True
                cursor = page.get("LastEvaluatedKey")
                if not cursor:
                    break
            if cursor:
                return True  # Conservative wait, not an unbounded lease inventory.
        return False

    @staticmethod
    def _references(row):
        refs = []
        if isinstance(row.get("source_ref"), dict):
            refs.append(row["source_ref"])
        evidence = row.get("evidence") or {}
        if isinstance(evidence.get("source_ref"), dict):
            refs.append(evidence["source_ref"])
        refs.extend(ref for ref in row.get("source_refs", []) if isinstance(ref, dict))
        return refs

    def _belongs(self, job, row):
        if job["scope"] == "group":
            return True
        if job["scope"] == "source":
            return row.get("source_id") == job["target"] or any(
                ref.get("source_id") == job["target"] for ref in self._references(row)
            )
        target = job["target"]
        if (
            row.get("actor_user_id") == target
            or row.get("subject_id") == "USER#" + target
            or row.get("rejected_by") == target
            or row.get("confirmed_by") == target
        ):
            return True
        if (row.get("evidence") or {}).get("actor_user_id") == target:
            return True
        if target in row.get("subject_ids", []) or target in row.get("evidence_authors", []):
            return True
        # Quarantined bodies intentionally have no duplicate actor field. Their
        # observation is ordered after CANDIDATE during the deletion scan.
        if row["sk"].startswith("CANDIDATE#"):
            ref = row["source_ref"]
            observation = self.repo.get_observation(job["pk"].removeprefix("CHAT#"), ref["source_id"])
            return observation.get("actor_user_id") == target
        return False

    def _fence(self, chat_id, job):
        control = self.repo.get_control(chat_id)
        if control["epoch"] != job["epoch"]:
            raise MemoryUnavailable("Deletion epoch changed unexpectedly")
        if job["scope"] == "group":
            if control["state"] != "STOPPING":
                raise MemoryUnavailable("Group deletion fence is missing")
            return [control]
        if control["state"] not in {"ACTIVE", "STOPPING"}:
            raise MemoryUnavailable("Deletion control is unavailable")
        if job["scope"] == "subject":
            subject = self.repo.get_subject(chat_id, job["target"])
            if not subject or subject["state"] != "STOPPING" or subject["generation"] != job["old_generation"] + 1:
                raise MemoryUnavailable("Subject deletion fence is missing")
            return [control, subject]
        observation = self.repo.get_observation(chat_id, job["target"])
        if not observation or not observation.get("deleted"):
            raise MemoryUnavailable("Source deletion fence is missing")
        return [control, observation]

    def _delete(self, row):
        operation = {"TableName": self.repo.table.name, "Key": {"pk": row["pk"], "sk": row["sk"]}}
        if "revision" in row:
            operation.update(
                ConditionExpression="#revision = :revision",
                ExpressionAttributeNames={"#revision": "revision"},
                ExpressionAttributeValues={":revision": row["revision"]},
            )
        else:
            operation["ConditionExpression"] = "attribute_exists(pk)"
        return {"Delete": operation}

    def _retained(self, job, row):
        if row["sk"] == "CONTROL" or row["sk"].startswith("PURGE#"):
            return True
        if row["sk"].startswith("SUBJECT#"):
            return True  # Generation/cutoff and explicit optout are anti-revival controls.
        if job["scope"] == "source" and row["sk"] == "OBSERVATION#" + job["target"]:
            return True  # Replaced with a minimal tombstone on completion.
        return False

    def advance(self, chat_id, job_key, *, max_pages=4):
        if not isinstance(job_key, str) or not job_key.startswith("PURGE#"):
            raise MemoryInputError("Expected deletion job identity")
        for _ in range(max(1, min(20, int(max_pages)))):
            job = self.repo._read(chat_id, job_key)
            if not job or job["state"] == "DONE":
                return job
            fences = self._fence(chat_id, job)
            if job["state"] == "DERIVED":
                return self._complete(chat_id, job)
            if job["state"] == "WAITING":
                # No new matching lease can pass its source/subject/control CAS
                # after begin(). Unbound answers conservatively cover the whole chat.
                if self._inflight(chat_id, job):
                    return job
                updated = {**job, "revision": int(job["revision"]) + 1, "state": "DELETING"}
                self.repo._transaction(
                    [*[self.repo._check_snapshot(row) for row in fences], self.repo._put_cas(updated, job)]
                )
                continue
            args = {"KeyConditionExpression": Key("pk").eq(chat_key(chat_id)), "ConsistentRead": True, "Limit": 40}
            if job.get("cursor"):
                args["ExclusiveStartKey"] = job["cursor"]
            page = self.repo.table.query(**args)
            rows = [row for row in page.get("Items", []) if not self._retained(job, row) and self._belongs(job, row)]
            updated = {
                **job,
                "revision": int(job["revision"]) + 1,
                "cursor": page.get("LastEvaluatedKey") or {},
                "deleted_rows": int(job["deleted_rows"]) + len(rows),
            }
            if not page.get("LastEvaluatedKey"):
                updated["state"] = "DERIVED"
            self.repo._transaction(
                [
                    *[self.repo._check_snapshot(row) for row in fences],
                    *[self._delete(row) for row in rows],
                    self.repo._put_cas(updated, job),
                ]
            )
            if updated["state"] == "DERIVED":
                return self._complete(chat_id, updated)
        return self.repo._read(chat_id, job_key)

    def _complete(self, chat_id, job):
        # Registered owners must report completion. A raised error or False leaves
        # the durable job fenced and recoverable, never a success confirmation.
        if any(cleaner(chat_id, job) is not True for cleaner in self.derived_cleaners):
            return job
        fences = self._fence(chat_id, job)
        now = self.repo.now()
        operations = []
        if job["scope"] == "group":
            control = fences[0]
            operations.append(
                self.repo._put_cas(
                    {
                        **control,
                        "revision": int(control["revision"]) + 1,
                        "state": "STOPPED",
                        "learning_enabled": False,
                        "purged_through": now,
                    },
                    control,
                )
            )
        elif job["scope"] == "subject":
            control, subject = fences
            operations.extend(
                [
                    self.repo._check_snapshot(control),
                    self.repo._put_cas(
                        {
                            **subject,
                            "revision": int(subject["revision"]) + 1,
                            "state": "ACTIVE",
                            "learning_started_at": now + 1,
                        },
                        subject,
                    ),
                ]
            )
        else:
            control, observation = fences
            tombstone = {key: observation[key] for key in ("pk", "sk", "source_id", "revision", "epoch")}
            tombstone.update(deleted=True, ambiguous=False, retained_evidence=False)
            tombstone["revision"] = int(observation["revision"]) + 1
            operations.extend([self.repo._check_snapshot(control), self.repo._put_cas(tombstone, observation)])
        done = {
            **job,
            "revision": int(job["revision"]) + 1,
            "state": "DONE",
            "completed_at": now,
            "ttl": now + 7 * 86400,
        }
        done.pop("actor_user_id", None)
        self.repo._transaction([*operations, self.repo._put_cas(done, job)])
        return done

    def recover(self, *, max_pages=2, runtime_seconds=20):
        deadline = time.monotonic() + max(1, min(60, runtime_seconds))
        checkpoint = self.repo.recovery_checkpoint("purges")
        cursor = checkpoint.get("cursor") or None
        attempted = failures = 0
        for _ in range(max(1, min(20, int(max_pages)))):
            if time.monotonic() >= deadline:
                break
            args = {
                "FilterExpression": Attr("kind").eq("PURGE") & Attr("state").ne("DONE"),
                "ConsistentRead": True,
                "Limit": 25,
            }
            if cursor:
                args["ExclusiveStartKey"] = cursor
            page = self.repo.table.scan(**args)
            for job in page.get("Items", []):
                if time.monotonic() >= deadline:
                    if failures:
                        raise MemoryPurgeRecoveryError("Some durable memory purges remain pending")
                    return {"attempted": attempted, "failures": failures, "pending": True}
                try:
                    self.advance(job["pk"].removeprefix("CHAT#"), job["sk"], max_pages=2)
                except Exception:
                    failures += 1  # No body/provider detail is persisted or logged.
                attempted += 1
            following = page.get("LastEvaluatedKey")
            self.repo.save_recovery_checkpoint("purges", checkpoint, following)
            checkpoint = self.repo.recovery_checkpoint("purges")
            cursor = following
            if not following:
                break
        if failures:
            raise MemoryPurgeRecoveryError("Some durable memory purges remain pending")
        return {"attempted": attempted, "failures": 0, "pending": bool(cursor)}
