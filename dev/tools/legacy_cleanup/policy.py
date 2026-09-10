"""Closed legacy type/resource policy, independent of live bot configuration."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal

MEMORY_PREFIXES = (
    "MSG#",
    "MEDIA_GROUP#",
    "USER#",
    "USERNAME#",
    "EVENT#",
    "USER_FACT#",
    "GROUP_FACT#",
    "JOKE#",
    "DAILY_SUMMARY#",
    "TERM#",
    "AGENT_REPLY#",
    "AMBIENT_REACTION#",
    "PROACTIVE#",
)
BOT_PREFIXES = ("BOT_COMMITMENT#", "BOT_CORRECTION#")
VECTOR_PREFIXES = ("EVENT#", "USER_FACT#", "GROUP_FACT#", "JOKE#", "DAILY_SUMMARY#")
CHAT_ID = re.compile(r"-?[1-9][0-9]{0,19}\Z")


class CleanupError(RuntimeError):
    """Fixed diagnostic codes only; never include item bodies or credential errors."""


@dataclass(frozen=True)
class Scope:
    account_id: str
    region: str
    table_arn: str
    index_arns: tuple[str, ...]
    chat_ids: tuple[str, ...] | None
    confirmed_bot_prefixes: tuple[str, ...] = ()

    def __post_init__(self):
        if not re.fullmatch(r"[0-9]{12}", self.account_id) or not re.fullmatch(r"[a-z]{2}-[a-z]+-[0-9]", self.region):
            raise CleanupError("invalid_account_or_region")
        prefix = f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/"
        if not self.table_arn.startswith(prefix) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{3,255}", self.table_arn[len(prefix) :]
        ):
            raise CleanupError("invalid_table_arn")
        vector_prefix = f"arn:aws:s3vectors:{self.region}:{self.account_id}:bucket/"
        if not self.index_arns or len(set(self.index_arns)) != len(self.index_arns):
            raise CleanupError("explicit_complete_legacy_indexes_required")
        for arn in self.index_arns:
            if not arn.startswith(vector_prefix) or not re.fullmatch(
                r"[a-z0-9.-]+/index/[a-z0-9.-]+", arn[len(vector_prefix) :]
            ):
                raise CleanupError("invalid_index_arn")
        if self.chat_ids is not None and (
            not self.chat_ids
            or len(set(self.chat_ids)) != len(self.chat_ids)
            or any(not isinstance(chat, str) or not CHAT_ID.fullmatch(chat) for chat in self.chat_ids)
        ):
            raise CleanupError("invalid_chat_scope")
        if any(prefix not in BOT_PREFIXES for prefix in self.confirmed_bot_prefixes):
            raise CleanupError("unconfirmed_bot_record_type")

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value) != {
            "account_id",
            "region",
            "table_arn",
            "index_arns",
            "chat_ids",
            "confirmed_bot_prefixes",
        }:
            raise CleanupError("invalid_scope_schema")
        return cls(
            **{
                **value,
                "index_arns": tuple(value["index_arns"]),
                "chat_ids": None if value["chat_ids"] is None else tuple(value["chat_ids"]),
                "confirmed_bot_prefixes": tuple(value["confirmed_bot_prefixes"]),
            }
        )

    def selected_chat(self, chat):
        return bool(CHAT_ID.fullmatch(chat)) and (self.chat_ids is None or chat in self.chat_ids)


def tagged(value):
    """Lossless deterministic JSON types for DDB decimal/binary/set snapshots."""
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise CleanupError("nonfinite_vector_value")
        return {"$float": value.hex()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, (bytes, bytearray)) or value.__class__.__name__ == "Binary":
        return {"$binary": base64.b64encode(bytes(value)).decode()}
    if isinstance(value, datetime):
        return {"$datetime": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, (set, frozenset)):
        return {"$set": sorted((tagged(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))}
    if isinstance(value, (list, tuple)):
        return [tagged(item) for item in value]
    if isinstance(value, dict):
        # A tagged map avoids collisions with an actual user field named $decimal.
        return {"$map": [[key, tagged(item)] for key, item in sorted(value.items())]}
    raise CleanupError("unsupported_snapshot_type")


def untagged(value):
    if isinstance(value, list):
        return [untagged(item) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"$map"}:
        return {key: untagged(item) for key, item in value["$map"]}
    if set(value) == {"$decimal"}:
        return Decimal(value["$decimal"])
    if set(value) == {"$float"}:
        return float.fromhex(value["$float"])
    if set(value) == {"$binary"}:
        return base64.b64decode(value["$binary"], validate=True)
    if set(value) == {"$datetime"}:
        return datetime.fromisoformat(value["$datetime"])
    if set(value) == {"$set"}:
        return set(untagged(item) for item in value["$set"])
    raise CleanupError("invalid_snapshot_encoding")


def canonical(value):
    return json.dumps(tagged(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def item_key(row):
    if not isinstance(row, dict) or not isinstance(row.get("pk"), str) or not isinstance(row.get("sk"), str):
        raise CleanupError("invalid_legacy_table_key")
    return {"pk": row["pk"], "sk": row["sk"]}


def classify(scope, row):
    key = item_key(row)
    pk, sk = key["pk"], key["sk"]
    if pk.startswith("MEMORY_VECTOR_DELETE#"):
        chat = pk.removeprefix("MEMORY_VECTOR_DELETE#")
        if not scope.selected_chat(chat):
            return "protected"
        vector_key = "memory/" + hashlib.sha256(f"{chat}:{sk}".encode()).hexdigest()
        if (
            not sk.startswith(VECTOR_PREFIXES)
            or str(row.get("chat_id")) != chat
            or row.get("vector_key") != vector_key
            or not isinstance(row.get("generation"), str)
            or not row["generation"]
        ):
            raise CleanupError("invalid_vector_delete_marker")
        return "vector_marker"
    if not pk.startswith("CHAT#") or not scope.selected_chat(pk.removeprefix("CHAT#")):
        return "protected"
    if sk == "VECTOR_BACKFILL":
        return "VECTOR_BACKFILL"
    for prefix in (*MEMORY_PREFIXES, *scope.confirmed_bot_prefixes):
        if sk.startswith(prefix):
            return prefix.rstrip("#")
    return "protected"
