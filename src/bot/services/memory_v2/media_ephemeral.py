"""One-day album references; never create sources, facts or retained media bodies."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from boto3.dynamodb.conditions import Key

from .models import MemoryConflict, MemoryInputError, MemoryUnavailable, SourceRef, chat_key, integer, positive_id

MEDIA_RETENTION_SECONDS = 86400
MAX_ALBUM_ITEMS = 10
MAX_EXPLICIT_ITEMS = 4
MEDIA_TYPES = {"photo", "image_document", "video", "voice", "audio", "pdf", "text_file", "code_file"}


def _album_prefix(media_group_id):
    if not isinstance(media_group_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", media_group_id):
        raise MemoryInputError("Invalid album identity")
    return "MEDIA_ALBUM#" + hashlib.sha256(media_group_id.encode()).hexdigest() + "#"


def _metadata(media_ref, *, source_ref, actor_user_id, media_group_id):
    if (
        not isinstance(media_ref, Mapping)
        or not isinstance(media_ref.get("media_type"), str)
        or media_ref["media_type"] not in MEDIA_TYPES
    ):
        raise MemoryInputError("Unsupported album media")
    item = {"media_type": media_ref["media_type"]}
    for key, limit in (("file_id", 512), ("file_unique_id", 160), ("mime_type", 120)):
        value = media_ref.get(key)
        if value is not None:
            if (
                not isinstance(value, str)
                or not value
                or len(value) > limit
                or not value.isascii()
                or not value.isprintable()
            ):
                raise MemoryInputError("Invalid bounded media metadata")
            item[key] = value
    if not item.get("file_id"):
        raise MemoryInputError("Missing album file reference")
    for key in ("file_size", "duration_seconds"):
        if media_ref.get(key) is not None:
            item[key] = integer(media_ref[key])
    for key, expected in (
        ("source_message_id", source_ref.source_id),
        ("source_user_id", actor_user_id),
        ("media_group_id", media_group_id),
    ):
        if media_ref.get(key) is not None and str(media_ref[key]) != expected:
            raise MemoryInputError("Album source identity changed")
    item.update(
        source_message_id=int(source_ref.source_id), source_user_id=actor_user_id, media_group_id=media_group_id
    )
    # Captions, filenames, usernames and display names are deliberately absent.
    return item


class EphemeralMediaRepository:
    """Use the V2 source owner and final revision fences for every cache operation.

    Returned references are a fresh snapshot, not a permit to reuse them in SQS.
    The explicit worker must reload/revalidate immediately before media download
    or model use. The public adapter owns authentication and the direct-media
    fallback when V2 is unavailable.
    """

    def __init__(self, repo):
        self.repo = repo

    def _checks(self, snapshots):
        unique = {}
        for row in snapshots:
            key = row["pk"], row["sk"]
            if key in unique and unique[key]["revision"] != row["revision"]:
                raise MemoryConflict("Album snapshot changed during reading")
            unique[key] = row
        return [self.repo._check_snapshot(row) for row in unique.values()]

    def _snapshot(self, chat_id, ref, actor_user_id, created_at):
        control, subject, source = self.repo._observation_snapshot(chat_id, ref, learning=False)
        if (
            source["actor_user_id"] != actor_user_id
            or source["original_sent_at"] != created_at
            or source["edited_at"] != 0
            or source["source_kind"] != "message"
            or created_at < max(control["learning_started_at"], subject["learning_started_at"])
            or created_at > self.repo.now()
            or created_at + MEDIA_RETENTION_SECONDS <= self.repo.now()
        ):
            raise MemoryUnavailable("Album source is unavailable")
        return control, subject, source

    def store(self, *, chat_id, media_group_id, source_ref: SourceRef, actor_user_id, created_at, media_ref):
        """Save an already observed, original personal message; replay never renews TTL."""
        pk = chat_key(chat_id)
        if not str(chat_id).startswith("-"):
            raise MemoryInputError("Album caching requires a group")
        prefix = _album_prefix(media_group_id)
        actor_user_id = positive_id(actor_user_id)
        integer(created_at, minimum=1)
        if not isinstance(source_ref, SourceRef):
            raise MemoryInputError("Expected current source reference")
        metadata = _metadata(
            media_ref, source_ref=source_ref, actor_user_id=actor_user_id, media_group_id=media_group_id
        )
        snapshots = self._snapshot(chat_id, source_ref, actor_user_id, created_at)
        item = {
            "pk": pk,
            "sk": prefix + source_ref.source_id.zfill(20),
            "kind": "ephemeral_media",
            "revision": 1,
            "epoch": source_ref.epoch,
            "actor_user_id": actor_user_id,
            "source_ref": source_ref.as_dict(),
            "subject_generation": snapshots[1]["generation"],
            "created_at": created_at,
            "ttl": created_at + MEDIA_RETENTION_SECONDS,
            "media_ref": metadata,
        }
        previous = self.repo._read(chat_id, item["sk"])
        if previous and previous != item:
            raise MemoryConflict("Album metadata cannot replace an existing source")
        operation = self.repo._check_snapshot(previous) if previous else self.repo._put_cas(item, {})
        self.repo._transaction([*self._checks(snapshots), operation])
        if item["ttl"] <= self.repo.now():
            raise MemoryUnavailable("Album expired during persistence")

    def get_refs(self, chat_id, media_group_id, *, max_items=MAX_EXPLICIT_ITEMS):
        """Return at most four current references, or fail closed for an invalid album."""
        integer(max_items, minimum=1)
        if max_items > MAX_EXPLICIT_ITEMS:
            raise MemoryInputError("Explicit album item limit exceeded")
        prefix = _album_prefix(media_group_id)
        if not str(chat_id).startswith("-"):
            raise MemoryInputError("Album caching requires a group")
        control = self.repo._active_control(chat_id, learning=False)
        response = self.repo.table.query(
            KeyConditionExpression=Key("pk").eq(chat_key(chat_id)) & Key("sk").begins_with(prefix),
            ConsistentRead=True,
            ScanIndexForward=True,
            Limit=MAX_ALBUM_ITEMS + 1,
        )
        rows = response.get("Items", [])
        if response.get("LastEvaluatedKey") or len(rows) > MAX_ALBUM_ITEMS:
            raise MemoryUnavailable("Album exceeds bounded inventory")
        snapshots, result, actors = [control], [], set()
        for row in rows:
            try:
                ref = SourceRef(
                    row["source_ref"]["source_id"], int(row["source_ref"]["source_version"]), row["source_ref"]["epoch"]
                )
                actor = positive_id(row["actor_user_id"])
                created_at = int(row["created_at"])
                current = self._snapshot(chat_id, ref, actor, created_at)
                if (
                    row["kind"] != "ephemeral_media"
                    or row["source_ref"] != ref.as_dict()
                    or row["created_at"] != created_at
                    or row["sk"] != prefix + ref.source_id.zfill(20)
                    or row["epoch"] != ref.epoch
                    or row["subject_generation"] != current[1]["generation"]
                    or row["ttl"] != created_at + MEDIA_RETENTION_SECONDS
                ):
                    raise MemoryUnavailable("Album scope is obsolete")
                raw_metadata = dict(row["media_ref"])
                for key in ("file_size", "duration_seconds"):
                    if key in raw_metadata:
                        raw_metadata[key] = int(raw_metadata[key])
                metadata = _metadata(raw_metadata, source_ref=ref, actor_user_id=actor, media_group_id=media_group_id)
                if metadata != row["media_ref"]:
                    raise MemoryUnavailable("Album metadata is not canonical")
            except (KeyError, TypeError, ValueError) as exc:
                raise MemoryUnavailable("Album metadata is invalid") from exc
            actors.add(actor)
            snapshots.extend((*current, row))
            result.append({**metadata, "ephemeral_source_ref": ref.as_dict()})
        if len(actors) > 1:
            raise MemoryUnavailable("Album has inconsistent ownership")
        self.repo._transaction(self._checks(snapshots))
        if any(int(row["ttl"]) <= self.repo.now() for row in rows):
            raise MemoryUnavailable("Album expired during reading")
        return result[:max_items]
