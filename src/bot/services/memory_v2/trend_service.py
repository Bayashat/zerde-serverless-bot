"""One bounded owner for source-derived topic contributions; never a fact writer."""

from __future__ import annotations

import time
from dataclasses import dataclass

from boto3.dynamodb.conditions import Key

from .models import ExtractionSource, MemoryConflict, MemoryInputError, MemoryUnavailable, SourceRef, chat_key, integer
from .trends import TOPIC_DICTIONARY_VERSION, WINDOW_SECONDS, TrendSnapshot, aggregate_trends

MAX_SELECTED_SOURCES = 20
MAX_QUERY_PAGE = 50
REFRESH_KEY = "TREND_REFRESH"


@dataclass(frozen=True)
class TrendProof:
    source_ref: SourceRef
    actor_user_id: str
    subject_generation: int
    subject_revision: int
    content_hash: str


@dataclass(frozen=True)
class TrendView:
    snapshot: TrendSnapshot
    coverage: dict
    source_refs: tuple[SourceRef, ...]
    evidence_authors: tuple[str, ...]
    proofs: tuple[TrendProof, ...]
    control_revision: int


class TrendService:
    """Persist labels per accepted source and read through current source owners.

    Cursor completion describes an inventory traversal, not a point-in-time
    database snapshot. Public sending must also bind source/author answer leases.
    """

    def __init__(self, repo):
        self.repo = repo

    @staticmethod
    def _key(ref):
        # Telegram message ids are monotonic within a chat. Fixed width makes
        # bounded descending reads prefer recent messages across digit changes.
        return f"TREND#{ref.source_id.zfill(20)}"

    @staticmethod
    def _source(chat_id, ref, head, raw):
        return ExtractionSource(
            str(chat_id),
            ref,
            str(head["actor_user_id"]),
            raw["text"],
            tuple((int(start), int(end)) for start, end in raw["quoted_spans"]),
            int(head["original_sent_at"]),
            int(head["edited_at"]),
        )

    def _snapshot(self, chat_id, ref):
        control, subject, head, raw = self.repo.source_snapshot(chat_id, ref, learning=False)
        observation = self.repo.get_observation(chat_id, ref.source_id)
        if (
            not observation
            or observation.get("deleted")
            or observation.get("ambiguous")
            or observation.get("revision") != ref.source_version
            or observation.get("epoch") != ref.epoch
            or observation.get("actor_user_id") != head["actor_user_id"]
            or observation.get("content_hash") != head["content_hash"]
            or observation.get("subject_generation") != subject["generation"]
        ):
            raise MemoryUnavailable("Trend source changed during lookup")
        now = self.repo.now()
        if int(head["original_sent_at"]) + WINDOW_SECONDS <= now or int(head["original_sent_at"]) > now:
            raise MemoryUnavailable("Trend source is outside its seven-day window")
        source = self._source(chat_id, ref, head, raw)
        return control, subject, head, raw, observation, source

    def contribute(self, chat_id, ref: SourceRef):
        """CAS one current contribution; infrastructure failures propagate."""
        control, subject, head, raw, observation, source = self._snapshot(chat_id, ref)
        now = self.repo.now()
        classified = aggregate_trends([source], chat_id=str(chat_id), epoch=ref.epoch, as_of=now)
        previous = self.repo._read(chat_id, self._key(ref))
        item = {
            "pk": chat_key(chat_id),
            "sk": self._key(ref),
            "kind": "TREND_CONTRIBUTION",
            "revision": int(previous.get("revision", 0)) + 1,
            "epoch": ref.epoch,
            "source_id": ref.source_id,
            "source_ref": ref.as_dict(),
            "actor_user_id": source.actor_user_id,
            "subject_generation": int(subject["generation"]),
            "content_hash": head["content_hash"],
            "original_sent_at": source.original_sent_at,
            "topics": [topic.topic for topic in classified.topics],
            "dictionary_version": TOPIC_DICTIONARY_VERSION,
            "updated_at": now,
            "expires_at": source.original_sent_at + WINDOW_SECONDS,
            "ttl": source.original_sent_at + WINDOW_SECONDS,
        }
        # Always fence the source and controls, even on a label-identical replay.
        # This prevents a worker that read before forget/edit from writing later.
        if self.repo.now() >= item["expires_at"]:
            raise MemoryUnavailable("Trend source expired before commit")
        self.repo._transaction(
            [
                *[self.repo._check_snapshot(row) for row in (control, subject, head, raw, observation)],
                self.repo._put_cas(item, previous),
            ]
        )
        return item

    @staticmethod
    def _cursor(chat_id, prefix, cursor):
        if cursor is None:
            return None
        if (
            not isinstance(cursor, dict)
            or set(cursor) != {"pk", "sk"}
            or cursor["pk"] != chat_key(chat_id)
            or not isinstance(cursor["sk"], str)
            or not cursor["sk"].startswith(prefix)
        ):
            raise MemoryInputError("Trend cursor does not belong to this scope")
        return dict(cursor)

    def _page(self, chat_id, prefix, cursor, page_size):
        args = {
            "KeyConditionExpression": Key("pk").eq(chat_key(chat_id)) & Key("sk").begins_with(prefix),
            "ConsistentRead": True,
            "ScanIndexForward": prefix != "TREND#",
            "Limit": min(MAX_QUERY_PAGE, integer(page_size, minimum=1)),
        }
        if cursor:
            args["ExclusiveStartKey"] = self._cursor(chat_id, prefix, cursor)
        return self.repo.table.query(**args)

    def _valid_contribution(self, chat_id, row, *, epoch):
        if (
            row.get("kind") != "TREND_CONTRIBUTION"
            or row.get("epoch") != epoch
            or row.get("dictionary_version") != TOPIC_DICTIONARY_VERSION
        ):
            raise MemoryUnavailable("Obsolete topic contribution")
        ref = SourceRef(**{**row["source_ref"], "source_version": int(row["source_ref"]["source_version"])})
        control, subject, head, _, _, source = self._snapshot(chat_id, ref)
        if (
            row.get("pk") != chat_key(chat_id)
            or row.get("sk") != self._key(ref)
            or ref.epoch != control["epoch"]
            or row.get("source_id") != ref.source_id
            or row.get("actor_user_id") != source.actor_user_id
            or row.get("subject_generation") != subject["generation"]
            or row.get("content_hash") != head["content_hash"]
            or int(row.get("expires_at", 0)) != source.original_sent_at + WINDOW_SECONDS
            or int(row["expires_at"]) <= self.repo.now()
        ):
            raise MemoryUnavailable("Topic contribution was invalidated")
        # Recompute the deterministic labels from the current canonical source;
        # stale/corrupt derived values can never introduce a topic or an author.
        classified = aggregate_trends([source], chat_id=str(chat_id), epoch=ref.epoch, as_of=self.repo.now())
        if row.get("topics") != [topic.topic for topic in classified.topics]:
            raise MemoryUnavailable("Topic contribution needs a dictionary refresh")
        proof = TrendProof(
            ref, source.actor_user_id, int(subject["generation"]), int(subject["revision"]), head["content_hash"]
        )
        return source, proof

    def read(self, chat_id, *, max_pages=2, page_size=20, max_sources=MAX_SELECTED_SOURCES, cursor=None):
        """Return a bounded view and explicit inventory/freshness limitations."""
        integer(max_pages, minimum=1)
        integer(max_sources, minimum=1)
        if max_pages > 20 or max_sources > MAX_SELECTED_SOURCES:
            raise MemoryInputError("Trend read exceeds bounded source/page limits")
        cursor = self._cursor(chat_id, "TREND#", cursor)
        control = self.repo._active_control(chat_id, learning=False)
        sources, proofs = [], []
        counts = {"scanned": 0, "accepted": 0, "obsolete": 0}
        following = cursor
        exhausted = False
        for _ in range(max_pages):
            page = self._page(chat_id, "TREND#", following, page_size)
            items = page.get("Items", [])
            for position, row in enumerate(items):
                counts["scanned"] += 1
                try:
                    source, proof = self._valid_contribution(chat_id, row, epoch=control["epoch"])
                except (MemoryUnavailable, MemoryInputError, KeyError, TypeError, ValueError):
                    counts["obsolete"] += 1
                else:
                    sources.append(source)
                    proofs.append(proof)
                    counts["accepted"] += 1
                if len(sources) >= max_sources:
                    has_more = position + 1 < len(items) or bool(page.get("LastEvaluatedKey"))
                    following = {"pk": row["pk"], "sk": row["sk"]} if has_more else None
                    exhausted = not has_more
                    break
            else:
                following = page.get("LastEvaluatedKey")
                exhausted = not following
            if exhausted or len(sources) >= max_sources:
                break
        if self.repo.get_control(chat_id)["revision"] != control["revision"]:
            raise MemoryConflict("Trend control changed during read")
        refresh = self.repo._read(chat_id, REFRESH_KEY)
        same_epoch = refresh.get("epoch") == control["epoch"]
        now = self.repo.now()
        snapshot = aggregate_trends(sources, chat_id=str(chat_id), epoch=control["epoch"], as_of=now)
        coverage = {
            **counts,
            "truncated": not exhausted,
            "cursor": following,
            "contribution_scan_complete": exhausted,
            "last_full_refresh_started_at": int(refresh.get("last_full_started_at", 0)) if same_epoch else 0,
            "last_full_refresh_completed_at": int(refresh.get("last_full_completed_at", 0)) if same_epoch else 0,
            "refresh_in_progress": bool(refresh.get("cursor")) if same_epoch else False,
            "inventory_verified": same_epoch and bool(refresh.get("last_full_completed_at")),
            "scope": "validated_contributions",
            "newer_sources_may_be_missing": True,
        }
        view = TrendView(
            snapshot,
            coverage,
            tuple(proof.source_ref for proof in proofs),
            tuple(sorted({proof.actor_user_id for proof in proofs})),
            tuple(proofs),
            int(control["revision"]),
        )
        self.validate_snapshot(view)
        return view

    def validate_snapshot(self, view: TrendView):
        """Recheck before presentation; public sending additionally needs a lease."""
        control = self.repo._active_control(view.snapshot.chat_id, learning=False)
        if control["epoch"] != view.snapshot.epoch or control["revision"] != view.control_revision:
            raise MemoryUnavailable("Trend snapshot control changed")
        if len(view.proofs) > MAX_SELECTED_SOURCES:
            raise MemoryInputError("Trend snapshot exceeds the source limit")
        if view.source_refs != tuple(proof.source_ref for proof in view.proofs) or view.evidence_authors != tuple(
            sorted({proof.actor_user_id for proof in view.proofs})
        ):
            raise MemoryInputError("Trend snapshot evidence identities do not match")
        checked = {(control["pk"], control["sk"]): control}
        for proof in view.proofs:
            source_control, subject, head, raw, observation, _ = self._snapshot(view.snapshot.chat_id, proof.source_ref)
            if (
                head["actor_user_id"] != proof.actor_user_id
                or head["content_hash"] != proof.content_hash
                or subject["generation"] != proof.subject_generation
                or subject["revision"] != proof.subject_revision
            ):
                raise MemoryUnavailable("Trend snapshot evidence changed")
            for row in (source_control, subject, head, raw, observation):
                key = row["pk"], row["sk"]
                if key in checked and checked[key]["revision"] != row["revision"]:
                    raise MemoryConflict("Trend evidence changed during validation")
                checked[key] = row
        # At most 20 sources: 1 control + 20 subjects + 60 source rows = 81.
        # All current pointers have one common validation point, even if an edit
        # happens while the bounded per-source reads are still in progress.
        now = self.repo.now()
        if any(
            row["sk"].startswith("HEAD#") and int(row["original_sent_at"]) + WINDOW_SECONDS <= now
            for row in checked.values()
        ):
            raise MemoryUnavailable("Trend evidence expired during validation")
        self.repo._transaction([self.repo._check_snapshot(row) for row in checked.values()])
        return True

    def refresh(self, chat_id, *, max_pages=2, page_size=20, runtime_seconds=20):
        """Resume one durable HEAD traversal; failed pages never advance the cursor."""
        integer(max_pages, minimum=1)
        integer(runtime_seconds, minimum=1)
        if max_pages > 20 or runtime_seconds > 60:
            raise MemoryInputError("Trend refresh exceeds bounded limits")
        deadline = time.monotonic() + runtime_seconds
        counts = {"scanned": 0, "updated": 0, "obsolete": 0, "pages": 0}
        for _ in range(max_pages):
            if time.monotonic() >= deadline:
                break
            control = self.repo._active_control(chat_id, learning=False)
            previous = self.repo._read(chat_id, REFRESH_KEY)
            current = previous if previous.get("epoch") == control["epoch"] else {}
            cursor = current.get("cursor") or None
            page = self._page(chat_id, "HEAD#", cursor, page_size)
            # Reprocessing an interrupted page is safe because contributions use
            # their source owner, not an unguarded cumulative count increment.
            for row in page.get("Items", []):
                if time.monotonic() >= deadline:
                    return {**counts, "pending": True, "page_restarted": True}
                counts["scanned"] += 1
                try:
                    ref = SourceRef(str(row["source_id"]), int(row["revision"]), str(row["epoch"]))
                    self.contribute(chat_id, ref)
                except (MemoryUnavailable, MemoryInputError, KeyError, TypeError, ValueError):
                    counts["obsolete"] += 1
                else:
                    counts["updated"] += 1
            next_cursor = page.get("LastEvaluatedKey") or {}
            now = self.repo.now()
            started = int(current.get("cycle_started_at", now)) if cursor else now
            item = {
                "pk": chat_key(chat_id),
                "sk": REFRESH_KEY,
                "kind": "TREND_REFRESH",
                "revision": int(previous.get("revision", 0)) + 1,
                "epoch": control["epoch"],
                "cursor": next_cursor,
                "cycle_started_at": started,
                "updated_at": now,
                "last_full_started_at": int(current.get("last_full_started_at", 0)),
                "last_full_completed_at": int(current.get("last_full_completed_at", 0)),
            }
            if not next_cursor:
                item.update(last_full_started_at=started, last_full_completed_at=now)
            self.repo._transaction([self.repo._check_snapshot(control), self.repo._put_cas(item, previous)])
            counts["pages"] += 1
            if not next_cursor:
                return {**counts, "pending": False, "last_full_refresh_completed_at": now}
        return {**counts, "pending": True}
