"""Durable deletion coordinator over the single V2 table and registered owners."""

from __future__ import annotations

import time

from boto3.dynamodb.conditions import Attr, Key

from .leases import ANSWER_LEASE_SECONDS
from .models import WORK_INDEX_NAME, MemoryConflict, MemoryInputError, MemoryUnavailable, chat_key, positive_id

PURGE_QUEUE = "MEMORY_PURGE"


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
            "work_queue": PURGE_QUEUE,
            "due_at": now,
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
                return (
                    row.get("actor_user_id") == job["target"]
                    or job["target"] in row.get("subject_ids", [])
                    or job["target"] in row.get("evidence_authors", [])
                )
            return any(ref.get("source_id") == job["target"] for ref in row.get("source_refs", []))
        if row.get("kind") == "WORK" and row.get("state") == "LEASED":
            return int(row.get("lease_until", 0)) > self.repo.now() and self._belongs(job, row)
        return False

    def _inflight(self, chat_id, job, *, deadline=None):
        # Every prior answer has a fixed <=360s lease and extraction <=130s.
        # begin() changes CONTROL revision, so a newly acquired answer cannot
        # bind a pre-deletion snapshot. This deadline bounds even a huge scan.
        if self.repo.now() >= int(job["created_at"]) + ANSWER_LEASE_SECONDS:
            return False
        for prefix in ("ANSWER_LEASE#", "WORK#"):
            cursor = None
            for _ in range(4):
                if deadline is not None and time.monotonic() >= deadline:
                    return True  # An incomplete lease inventory never permits deletion.
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
        if row["sk"].startswith("CONTROL_COMMAND#"):
            return True  # Body-free, seven-day command tombstones prevent destructive replay.
        if row["sk"] == "CONTROL" or row["sk"].startswith("PURGE#"):
            return True
        if row["sk"].startswith("SUBJECT#"):
            return True  # Generation/cutoff and explicit optout are anti-revival controls.
        if job["scope"] == "source" and row["sk"] == "OBSERVATION#" + job["target"]:
            return True  # Replaced with a minimal tombstone on completion.
        return False

    def advance(self, chat_id, job_key, *, max_pages=4, deadline=None):
        if not isinstance(job_key, str) or not job_key.startswith("PURGE#"):
            raise MemoryInputError("Expected deletion job identity")
        for _ in range(max(1, min(20, int(max_pages)))):
            job = self.repo._read(chat_id, job_key)
            if not job or job["state"] == "DONE":
                return job
            if deadline is not None and time.monotonic() >= deadline:
                return job
            fences = self._fence(chat_id, job)
            if deadline is not None and time.monotonic() >= deadline:
                return job
            if job["state"] == "DERIVED":
                return self._complete(chat_id, job, deadline=deadline)
            if job["state"] == "WAITING":
                # No new matching lease can pass its source/subject/control CAS
                # after begin(). Unbound answers conservatively cover the whole chat.
                if self._inflight(chat_id, job, deadline=deadline):
                    return job
                if deadline is not None and time.monotonic() >= deadline:
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
            if deadline is not None and time.monotonic() >= deadline:
                return job
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
                return self._complete(chat_id, updated, deadline=deadline)
        return self.repo._read(chat_id, job_key)

    def _complete(self, chat_id, job, *, deadline=None):
        # Registered owners must report completion. A raised error or False leaves
        # the durable job fenced and recoverable, never a success confirmation.
        for cleaner in self.derived_cleaners:
            if deadline is not None and time.monotonic() >= deadline:
                return job
            if cleaner(chat_id, job) is not True:
                return job
        if deadline is not None and time.monotonic() >= deadline:
            return job
        fences = self._fence(chat_id, job)
        if deadline is not None and time.monotonic() >= deadline:
            return job
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
        done.pop("work_queue", None)
        done.pop("due_at", None)
        self.repo._transaction([*operations, self.repo._put_cas(done, job)])
        return done

    def _index_legacy(self, candidate):
        chat_id = candidate["pk"].removeprefix("CHAT#")
        job = self.repo._read(chat_id, candidate["sk"])
        if not job or job.get("kind") != "PURGE" or job["state"] == "DONE" or "work_queue" in job:
            return
        fences = self._fence(chat_id, job)
        updated = {
            **job,
            "revision": int(job["revision"]) + 1,
            "work_queue": PURGE_QUEUE,
            "due_at": int(job["created_at"]),
        }
        self.repo._transaction([*[self.repo._check_snapshot(row) for row in fences], self.repo._put_cas(updated, job)])

    def _advance_due(self, candidate, deadline):
        chat_id = candidate["pk"].removeprefix("CHAT#")
        job = self.repo._read(chat_id, candidate["sk"])
        # KEYS_ONLY index entries can be stale, duplicated or not yet visible.
        # The strong base read and advance's original fences alone permit work.
        if (
            job
            and job.get("kind") == "PURGE"
            and job["state"] != "DONE"
            and job.get("work_queue") == PURGE_QUEUE
            and job.get("due_at", self.repo.now() + 1) <= self.repo.now()
        ):
            result = self.advance(chat_id, job["sk"], max_pages=20, deadline=deadline)
            return result.get("state") != "DONE"
        return False

    def _recover_pages(self, name, fetch, process, key_fields, *, max_pages, deadline):
        checkpoint = self.repo.recovery_checkpoint(name)
        cursor = checkpoint.get("cursor") or None
        attempted = failures = 0
        unfinished = False
        for _ in range(max_pages):
            if time.monotonic() >= deadline:
                return attempted, failures, True
            page = fetch(cursor)
            for candidate in page.get("Items", []):
                if time.monotonic() >= deadline:
                    return attempted, failures, True
                try:
                    unfinished |= bool(process(candidate))
                except Exception:
                    failures += 1  # No body/provider detail is persisted or logged.
                attempted += 1
                # Checkpoint each attempted hint, including WAITING, partial and
                # failed jobs. A large/poison job cannot own the start of every run.
                following = {key: candidate[key] for key in key_fields}
                try:
                    checkpoint = self.repo.save_recovery_checkpoint(name, checkpoint, following)
                except MemoryConflict:
                    return attempted, failures, True  # Another runner owns progress.
            following = page.get("LastEvaluatedKey")
            try:
                checkpoint = self.repo.save_recovery_checkpoint(name, checkpoint, following)
            except MemoryConflict:
                return attempted, failures, True
            cursor = following
            if not following:
                break
        return attempted, failures, unfinished or bool(cursor)

    def recover(self, *, max_pages=2, runtime_seconds=20):
        started = time.monotonic()
        duration = max(1, min(60, runtime_seconds))
        deadline = started + duration
        max_pages = max(1, min(20, int(max_pages)))

        def legacy_page(cursor):
            return self.repo.table.scan(
                FilterExpression=Attr("kind").eq("PURGE") & Attr("state").ne("DONE") & Attr("work_queue").not_exists(),
                ConsistentRead=True,
                Limit=25,
                **({"ExclusiveStartKey": cursor} if cursor else {}),
            )

        def due_page(cursor):
            return self.repo.table.query(
                IndexName=WORK_INDEX_NAME,
                KeyConditionExpression=Key("work_queue").eq(PURGE_QUEUE) & Key("due_at").lte(self.repo.now()),
                Limit=10,
                **({"ExclusiveStartKey": cursor} if cursor else {}),
            )

        failures, pending, counts = 0, False, {}
        for name, fetch, process, keys, lane_deadline in (
            # Old deployments need bounded discovery once, not a full-table tour
            # before every advance. Reserve time even under a busy indexed lane.
            ("purges", legacy_page, self._index_legacy, ("pk", "sk"), started + min(5, duration / 4)),
            (
                "purge_due",
                due_page,
                lambda candidate: self._advance_due(candidate, deadline),
                ("pk", "sk", "work_queue", "due_at"),
                deadline,
            ),
        ):
            try:
                count, failed, more = self._recover_pages(
                    name, fetch, process, keys, max_pages=max_pages, deadline=lane_deadline
                )
                counts[name] = count
                failures += failed
                pending |= more
            except Exception:
                failures += 1  # One unavailable lane must not block the other.
        if failures:
            raise MemoryPurgeRecoveryError("Some durable memory purges remain pending")
        return {
            "attempted": counts["purge_due"],
            "legacy_candidates": counts["purges"],
            "failures": 0,
            "pending": pending,
        }
