"""Reference-only batch worker. FactWriter remains the sole fact mutation owner."""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict

from .models import ExtractionResult, MemoryConflict, MemoryInputError, MemoryUnavailable, SourceRef, chat_key
from .writer import FactWriter


class MemoryWorker:
    def __init__(self, repo, extractor_factory, *, sizing_fn, runtime_seconds=100):
        self.repo = repo
        self.writer = FactWriter(repo)
        self.extractor = extractor_factory(self.validate_sources)
        self.sizing_fn = sizing_fn
        self.runtime_seconds = min(100, max(1, runtime_seconds))
        self._leases = {}

    @staticmethod
    def _key(chat_id, ref):
        return str(chat_id), ref.source_id, ref.source_version, ref.epoch

    async def validate_sources(self, sources):
        for source in sources:
            lease = self._leases.get(self._key(source.chat_id, source.ref))
            if lease is None or self.repo.valid_leased_source(source.chat_id, lease) != source:
                raise MemoryUnavailable("Model source changed or is no longer leased")

    @staticmethod
    def _parse(record):
        payload = json.loads(record["body"])
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "task_type", "chat_id", "source_ref"}
            or type(payload["schema"]) is not int
            or payload["schema"] != 2
            or payload["task_type"] != "PROCESS_MEMORY_V2"
        ):
            raise MemoryInputError("Invalid Memory V2 task envelope")
        chat_key(payload["chat_id"])
        raw = payload["source_ref"]
        if not isinstance(raw, dict) or set(raw) != {"source_id", "source_version", "epoch"}:
            raise MemoryInputError("Invalid Memory V2 source reference")
        return str(payload["chat_id"]), SourceRef(**raw)

    def _retry(self, source, *, reason="retry", retry_at=None):
        lease = self._leases[self._key(source.chat_id, source.ref)]
        reason = {
            "budget_unavailable": "budget",
            "budget_settlement_unavailable": "budget",
            "daily_quota_unavailable": "quota",
            "daily_quota_exhausted": "quota",
            "provider_or_schema_unavailable": "provider",
        }.get(reason, reason)
        return self.repo.retry_work(source.chat_id, lease, retry_at=retry_at or self.repo.now() + 60, reason=reason)

    def _invalid(self, source):
        lease = self._leases[self._key(source.chat_id, source.ref)]
        try:
            self.repo.source_snapshot(source.chat_id, source.ref, learning=False)
        except MemoryUnavailable:
            self.repo.finish_work(source.chat_id, source.ref, outcome="EXPIRED", reason="source_revoked", lease=lease)
        else:
            self._retry(source, reason="paused")

    async def _run_batch(self, batch, timeout):
        try:
            await self.validate_sources(batch)
        except MemoryUnavailable:
            for source in batch:
                self._invalid(source)
            return
        try:
            results = await asyncio.wait_for(self.extractor.extract_batch(batch), timeout=timeout)
        except MemoryUnavailable:
            for source in batch:
                self._invalid(source)
            return
        except MemoryInputError:
            for source in batch:
                self.repo.finish_work(
                    source.chat_id,
                    source.ref,
                    outcome="FAILED",
                    reason="invalid_source",
                    lease=self._leases[self._key(source.chat_id, source.ref)],
                )
            return
        except Exception:
            # Provider details are deliberately not logged/persisted here.
            for source in batch:
                self._retry(source, reason="provider")
            return
        expected = {source.ref for source in batch}
        if (
            not isinstance(results, list)
            or len(results) != len(expected)
            or any(not isinstance(result, ExtractionResult) for result in results)
            or {result.ref for result in results} != expected
        ):
            for source in batch:
                self._retry(source, reason="schema")
            return
        by_ref = {source.ref: source for source in batch}
        for result in results:
            source = by_ref[result.ref]
            if result.status == "defer":
                self._retry(source, reason=result.reason, retry_at=result.retry_at)
                continue
            if result.status != "complete" or not isinstance(result.changes, tuple):
                self._retry(source, reason="schema")
                continue
            lease = self._leases[self._key(source.chat_id, source.ref)]
            try:
                self.repo.valid_leased_source(source.chat_id, lease)
                subject = self.repo.get_subject(source.chat_id, source.actor_user_id)
                self.writer.apply_source_changes(
                    source.chat_id,
                    source.ref,
                    subject_generation=lease.subject_generation,
                    expected_subject_revision=int(subject["revision"]),
                    changes=list(result.changes),
                    lease=lease,
                )
            except MemoryConflict:
                self._retry(source, reason="conflict")
            except MemoryUnavailable:
                self._invalid(source)
            except MemoryInputError:
                self._retry(source, reason="schema")

    async def handle_records(self, records):
        started = time.monotonic()
        failed = set()
        groups = defaultdict(list)
        record_ids = defaultdict(list)
        self._leases = {}
        try:
            for record in records:
                identifier = record["messageId"]
                lease = None
                try:
                    chat_id, ref = self._parse(record)
                    key = self._key(chat_id, ref)
                    record_ids[key].append(identifier)
                    if key in self._leases:
                        continue
                    lease = self.repo.claim_work(chat_id, ref)
                    if lease is None:
                        continue
                    self._leases[key] = lease
                    source = self.repo.valid_leased_source(chat_id, lease)
                    groups[chat_id].append(source)
                except MemoryUnavailable:
                    # Valid source references may be revoked between claim and read.
                    if lease:
                        self.repo.retry_work(chat_id, lease, retry_at=self.repo.now() + 60, reason="paused")
                except Exception:
                    failed.add(identifier)
            for sources in groups.values():
                batches, batch = [], []
                for source in sources:
                    if self.sizing_fn([source]) > 8000:
                        self.repo.finish_work(
                            source.chat_id,
                            source.ref,
                            outcome="FAILED",
                            reason="input_limit",
                            lease=self._leases[self._key(source.chat_id, source.ref)],
                        )
                        continue
                    if batch and (len(batch) >= 20 or self.sizing_fn([*batch, source]) > 8000):
                        batches.append(batch)
                        batch = []
                    batch.append(source)
                if batch:
                    batches.append(batch)
                for batch in batches:
                    remaining = self.runtime_seconds - (time.monotonic() - started)
                    if remaining < 45:
                        for source in batch:
                            self._retry(source, retry_at=self.repo.now() + 30)
                        continue
                    try:
                        await self._run_batch(batch, min(50, remaining - 5))
                    except Exception:
                        for source in batch:
                            failed.update(record_ids[self._key(source.chat_id, source.ref)])
        finally:
            self._leases = {}
        return {"batchItemFailures": [{"itemIdentifier": identifier} for identifier in sorted(failed)]}
