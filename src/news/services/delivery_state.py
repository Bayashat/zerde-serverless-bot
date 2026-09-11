"""The stats table owns frozen news manifests and exact per-chat delivery receipts."""

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

LEASE_SECONDS = 360  # Deployment must keep News Lambda timeout below this value.
RETENTION_SECONDS = 30 * 86400
MAX_JOB_AGE_SECONDS = 36 * 3600


class NewsStateError(RuntimeError):
    pass


def _conditional(exc):
    return exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def parse_job(event):
    """Use scheduled time, never invocation/retry time, as the daily news identity."""
    stamp = event.get("scheduled_at")
    if not isinstance(stamp, str):
        raise ValueError("scheduled_at from the original scheduled event is required")
    scheduled = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if scheduled.tzinfo is None:
        raise ValueError("scheduled_at must contain a timezone")
    scheduled = scheduled.astimezone(timezone.utc)
    age = time.time() - scheduled.timestamp()
    if age < -300 or age > MAX_JOB_AGE_SECONDS:
        raise ValueError("News scheduled event is outside its delivery window")
    lang = event.get("lang")
    if lang not in {"kk", "zh", "ru"}:
        raise ValueError("Unsupported news language")
    slot = event.get("schedule_slot") or scheduled.strftime("%H%M")
    if not isinstance(slot, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", slot):
        raise ValueError("Invalid news schedule slot")
    raw_chats = event.get("chat_ids")
    if isinstance(raw_chats, (str, int)):
        raw_chats = [raw_chats]
    if not isinstance(raw_chats, list) or not raw_chats or len(raw_chats) > 100:
        raise ValueError("News needs a bounded list of chat IDs")
    chats = sorted({str(chat) for chat in raw_chats})
    if any(not re.fullmatch(r"-[1-9][0-9]*", chat) for chat in chats):
        raise ValueError("News destinations must be group chat IDs")
    day = scheduled.astimezone(ZoneInfo("Asia/Almaty")).date().isoformat()
    return {
        "job_id": f"{day}#{lang}#{slot}",
        "scheduled_at": scheduled.isoformat(),
        "date": day,
        "lang": lang,
        "slot": slot,
        "chat_ids": chats,
    }


class NewsDeliveryRepository:
    def __init__(self, table=None):
        self.table = table

    def _table(self):
        if self.table is None:
            self.table = boto3.resource(
                "dynamodb", config=Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1})
            ).Table(os.environ["STATS_TABLE_NAME"])
        return self.table

    @staticmethod
    def manifest_key(job_id):
        return {"stat_key": f"news_manifest#{job_id}"}

    @staticmethod
    def delivery_key(job_id, chat_id):
        return {"stat_key": f"news_delivery#{job_id}#{chat_id}"}

    def get_manifest(self, job_id):
        return self._table().get_item(Key=self.manifest_key(job_id), ConsistentRead=True).get("Item") or {}

    def claim_manifest(self, job):
        owner = uuid.uuid4().hex
        now = int(time.time())
        try:
            response = self._table().update_item(
                Key=self.manifest_key(job["job_id"]),
                UpdateExpression=(
                    "SET #state = :building, lease_owner = :owner, lease_until = :until, "
                    "job_id = :job, scheduled_at = :scheduled, chat_ids = :chats, #ttl = :ttl"
                ),
                ConditionExpression=(
                    "(attribute_not_exists(#state) OR #state = :building) AND "
                    "(attribute_not_exists(lease_owner) OR lease_until < :now) AND "
                    "(attribute_not_exists(scheduled_at) OR scheduled_at = :scheduled) AND "
                    "(attribute_not_exists(chat_ids) OR chat_ids = :chats)"
                ),
                ExpressionAttributeNames={"#state": "state", "#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":building": "BUILDING",
                    ":owner": owner,
                    ":until": now + LEASE_SECONDS,
                    ":now": now,
                    ":job": job["job_id"],
                    ":scheduled": job["scheduled_at"],
                    ":chats": job["chat_ids"],
                    ":ttl": now + RETENTION_SECONDS,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional(exc):
                current = self.get_manifest(job["job_id"])
                if (
                    current.get("state") == "READY"
                    and current.get("scheduled_at") == job["scheduled_at"]
                    and current.get("chat_ids") == job["chat_ids"]
                ):
                    return None, current
                raise NewsStateError("News manifest is busy or event identity changed") from None
            raise
        return owner, response["Attributes"]

    def freeze_manifest(self, job, owner, steps):
        wire = json.dumps(steps, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if len(wire) > 64000:
            raise ValueError("News manifest exceeds its size limit")
        digest = hashlib.sha256(wire).hexdigest()
        response = self._table().update_item(
            Key=self.manifest_key(job["job_id"]),
            UpdateExpression=(
                "SET #state = :ready, steps = :steps, content_hash = :hash " "REMOVE lease_owner, lease_until"
            ),
            ConditionExpression="#state = :building AND lease_owner = :owner",
            ExpressionAttributeNames={"#state": "state"},
            ExpressionAttributeValues={
                ":ready": "READY",
                ":building": "BUILDING",
                ":owner": owner,
                ":steps": steps,
                ":hash": digest,
            },
            ReturnValues="ALL_NEW",
        )
        return response["Attributes"]

    def release_manifest(self, job, owner):
        self._release(self.manifest_key(job["job_id"]), owner)

    def _release(self, key, owner):
        try:
            self._table().update_item(
                Key=key,
                UpdateExpression="REMOVE lease_owner, lease_until",
                ConditionExpression="lease_owner = :owner",
                ExpressionAttributeValues={":owner": owner},
            )
        except ClientError as exc:
            if not _conditional(exc):
                raise

    def get_delivery(self, job_id, chat_id):
        return self._table().get_item(Key=self.delivery_key(job_id, chat_id), ConsistentRead=True).get("Item") or {}

    def claim_delivery(self, manifest, chat_id):
        if str(chat_id) not in manifest["chat_ids"]:
            raise NewsStateError("Chat is not in this frozen news manifest")
        key = self.delivery_key(manifest["job_id"], chat_id)
        now = int(time.time())
        owner = uuid.uuid4().hex
        initial_steps = [
            {"state": "PENDING", "mode": "photo" if step.get("image_url") else "text", "attempt": 0}
            for step in manifest["steps"]
        ]
        try:
            result = self._table().update_item(
                Key=key,
                UpdateExpression=(
                    "SET content_hash = if_not_exists(content_hash, :hash), "
                    "steps = if_not_exists(steps, :steps), revision = if_not_exists(revision, :zero), "
                    "lease_owner = :owner, lease_until = :until, #ttl = :ttl"
                ),
                ConditionExpression=(
                    "(attribute_not_exists(content_hash) OR content_hash = :hash) AND "
                    "(attribute_not_exists(lease_owner) OR lease_until < :now)"
                ),
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={
                    ":hash": manifest["content_hash"],
                    ":steps": initial_steps,
                    ":zero": 0,
                    ":owner": owner,
                    ":until": now + LEASE_SECONDS,
                    ":now": now,
                    ":ttl": now + RETENTION_SECONDS,
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if _conditional(exc):
                raise NewsStateError("News chat delivery is busy or content identity changed") from None
            raise
        return owner, result["Attributes"]

    def save_step(self, row, owner, index, step):
        steps = [dict(item) for item in row["steps"]]
        steps[index] = step
        revision = int(row["revision"]) + 1
        self._table().update_item(
            Key={"stat_key": row["stat_key"]},
            UpdateExpression="SET steps = :steps, revision = :next",
            ConditionExpression="content_hash = :hash AND lease_owner = :owner AND revision = :revision",
            ExpressionAttributeValues={
                ":steps": steps,
                ":next": revision,
                ":hash": row["content_hash"],
                ":owner": owner,
                ":revision": row["revision"],
            },
        )
        row.update(steps=steps, revision=revision)

    def release_delivery(self, row, owner):
        self._release({"stat_key": row["stat_key"]}, owner)

    def repair_unknown(
        self,
        *,
        job_id,
        chat_id,
        content_hash,
        step_index,
        attempt_id,
        expected_revision,
        resolution,
        note,
        message_id=None,
    ):
        """Explicit operator-only CAS repair; never invoked automatically by the scheduled handler."""
        if resolution not in {"CONFIRM_SENT", "REOPEN"} or not note or len(note) > 200:
            raise ValueError("Explicit repair resolution and a short operator note are required")
        manifest = self.get_manifest(job_id)
        row = self.get_delivery(job_id, chat_id)
        if (
            manifest.get("content_hash") != content_hash
            or row.get("content_hash") != content_hash
            or str(chat_id) not in manifest.get("chat_ids", [])
            or row.get("revision") != expected_revision
        ):
            raise NewsStateError("News repair identity no longer matches")
        if type(step_index) is not int or not 0 <= step_index < len(row["steps"]):
            raise ValueError("Invalid repair step")
        step = dict(row["steps"][step_index])
        if step.get("state") != "UNKNOWN" or step.get("attempt_id") != attempt_id:
            raise NewsStateError("Only this exact unknown delivery attempt can be repaired")
        if resolution == "CONFIRM_SENT":
            if type(message_id) is not int or message_id <= 0:
                raise ValueError("Confirmed repair needs the actual Telegram message ID")
            step.update(state="SENT", message_id=message_id)
        else:
            if time.time() - datetime.fromisoformat(manifest["scheduled_at"]).timestamp() > MAX_JOB_AGE_SECONDS:
                raise NewsStateError("Expired news cannot be reopened for automatic delivery")
            step.update(state="PENDING", not_before=0)
        step.update(repair_note=note, repaired_at=int(time.time()))
        steps = [dict(item) for item in row["steps"]]
        steps[step_index] = step
        self._table().update_item(
            Key=self.delivery_key(job_id, chat_id),
            UpdateExpression="SET steps = :steps, revision = :next",
            ConditionExpression=(
                "content_hash = :hash AND revision = :revision AND "
                "(attribute_not_exists(lease_owner) OR lease_until < :now)"
            ),
            ExpressionAttributeValues={
                ":steps": steps,
                ":next": int(expected_revision) + 1,
                ":hash": content_hash,
                ":revision": expected_revision,
                ":now": int(time.time()),
            },
        )
