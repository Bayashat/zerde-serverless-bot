"""Bounded recovery over durable cursors; an empty filtered page is not EOF."""

import logging
import time

from .models import WORK_SHARDS, MemoryConflict, SourceRef

logger = logging.getLogger(__name__)


class MemoryRecoveryError(RuntimeError):
    """Some durable work remains retryable; no failed receipt was acknowledged."""


class MemoryRecovery:
    def __init__(self, ingestion, *, runtime_seconds=90):
        self.ingestion = ingestion
        self.repo = ingestion.repo
        self.runtime_seconds = min(90, max(1, runtime_seconds))
        self._deadline = 0
        self._failures = 0

    def _pages(self, name, fetch, process, max_pages):
        checkpoint = self.repo.recovery_checkpoint(name)
        cursor = checkpoint.get("cursor") or None
        total = 0
        for _ in range(max_pages):
            if time.monotonic() >= self._deadline:
                return total
            rows, following = fetch(cursor)
            for row in rows:
                if time.monotonic() >= self._deadline:
                    return total
                try:
                    process(row)
                except Exception as exc:
                    # Keep the durable row pending, but do not let a poison receipt
                    # starve later pages. A full sweep will revisit it; the run fails
                    # visibly after other independent work has progressed.
                    self._failures += 1
                    logger.warning(
                        "Memory recovery item remains pending", extra={"lane": name, "error_type": type(exc).__name__}
                    )
                total += 1
            # Every row was attempted; failed rows stay pending for the next sweep.
            # Lost checkpoints cause safe replay; competing runners cannot overwrite.
            try:
                self.repo.save_recovery_checkpoint(name, checkpoint, following)
            except MemoryConflict:
                return total
            checkpoint = self.repo.recovery_checkpoint(name)
            cursor = following
            if not following:
                break
        return total

    def run(self, *, max_pages=4):
        self._deadline = time.monotonic() + self.runtime_seconds
        self._failures = 0
        max_pages = max(1, min(20, int(max_pages)))
        counts = {}
        for shard in range(WORK_SHARDS):

            def enqueue(row):
                ref = SourceRef(**{**row["source_ref"], "source_version": int(row["source_ref"]["source_version"])})
                chat_id = row["pk"].removeprefix("CHAT#")
                if int(row["expires_at"]) <= self.repo.now():
                    self.repo.finish_work(chat_id, ref, outcome="EXPIRED", reason="source_expired")
                else:
                    try:
                        self.repo.note_recovery(chat_id, ref)
                    except MemoryConflict:
                        pass  # A worker can win this diagnostic-only race.
                    self.ingestion.enqueue(chat_id, ref, strict=True)

            counts[f"work{shard}"] = self._pages(
                f"work{shard}",
                lambda cursor, current_shard=shard: self.repo.list_due_work(current_shard, cursor=cursor),
                enqueue,
                max_pages,
            )

        def expire(row):
            if row["state"] == "ACCEPTED":
                self.ingestion.promote_clean(row["receipt_case_id"])
                return
            if int(row["expires_at"]) <= self.repo.now():
                raw = row["source_ref"]
                ref = SourceRef(raw["source_id"], int(raw["source_version"]), raw["epoch"])
                self.repo.finish_admission(row["pk"].removeprefix("CHAT#"), ref, outcome="EXPIRED")

        counts["admissions"] = self._pages(
            "admissions", lambda cursor: self.repo.list_pending_admissions(cursor=cursor), expire, max_pages
        )
        counts["clean"] = self._pages(
            "clean",
            lambda cursor: self.ingestion.moderation_repo.list_clean_pending(cursor=cursor),
            lambda row: self.ingestion.promote_clean(row["case_id"]),
            max_pages,
        )
        if self._failures:
            raise MemoryRecoveryError(f"{self._failures} recovery items remain pending")
        return counts
