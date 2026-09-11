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
POSITIVE_ID = re.compile(r"[1-9][0-9]{0,19}\Z")


class CleanupError(RuntimeError):
    """Fixed diagnostic codes only; never include item bodies or credential errors."""


@dataclass(frozen=True)
class RetiredContest:
    chat_id: str
    root_message_id: str

    def __post_init__(self):
        if (
            not isinstance(self.chat_id, str)
            or not CHAT_ID.fullmatch(self.chat_id)
            or not isinstance(self.root_message_id, str)
            or not POSITIVE_ID.fullmatch(self.root_message_id)
        ):
            raise CleanupError("invalid_retired_contest_identity")


@dataclass(frozen=True)
class Scope:
    account_id: str
    region: str
    table_arn: str
    index_arns: tuple[str, ...]
    chat_ids: tuple[str, ...] | None
    confirmed_bot_prefixes: tuple[str, ...] = ()
    retired_contests: tuple[RetiredContest, ...] = ()

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
        if (
            not isinstance(self.retired_contests, tuple)
            or any(not isinstance(contest, RetiredContest) for contest in self.retired_contests)
            or len(set(self.retired_contests)) != len(self.retired_contests)
            or any(not self.selected_chat(contest.chat_id) for contest in self.retired_contests)
        ):
            raise CleanupError("invalid_or_out_of_scope_retired_contests")

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        required = {
            "account_id",
            "region",
            "table_arn",
            "index_arns",
            "chat_ids",
            "confirmed_bot_prefixes",
        }
        if not isinstance(value, dict) or set(value) not in (required, required | {"retired_contests"}):
            raise CleanupError("invalid_scope_schema")
        contests = value.get("retired_contests", [])
        if not isinstance(contests, (list, tuple)) or any(
            not isinstance(contest, dict) or set(contest) != {"chat_id", "root_message_id"} for contest in contests
        ):
            raise CleanupError("invalid_retired_contest_scope_schema")
        return cls(
            **{
                **value,
                "index_arns": tuple(value["index_arns"]),
                "chat_ids": None if value["chat_ids"] is None else tuple(value["chat_ids"]),
                "confirmed_bot_prefixes": tuple(value["confirmed_bot_prefixes"]),
                "retired_contests": tuple(RetiredContest(**contest) for contest in contests),
            }
        )

    def selected_chat(self, chat):
        return bool(CHAT_ID.fullmatch(chat)) and (self.chat_ids is None or chat in self.chat_ids)

    def selected_contest(self, chat, root):
        return any(contest.chat_id == chat and contest.root_message_id == root for contest in self.retired_contests)


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


def _positive_number(value):
    """Identifiers/timestamps written as DDB numbers must remain integral, not bool."""
    return (
        (type(value) is int or isinstance(value, Decimal))
        and (not isinstance(value, Decimal) or value.is_finite())
        and value > 0
        and value == int(value)
    )


def _retired_contest_kind(scope, row, pk, sk):
    """Only four historical shapes; no arbitrary CONTEST/CHAT prefix deletion.

    A missing META is allowed: physical TTL may already have removed it. Each
    surviving row must independently prove the explicitly selected chat/root.
    """
    if not scope.retired_contests:
        return "protected"
    if pk == "CONTEST_TTL_OUTBOX":
        match = re.fullmatch(r"CHAT#(-?[1-9][0-9]{0,19})#ROOT#([0-9]{13,20})", sk)
        if not match:
            return "protected"
        chat, root_key = match.groups()
        root = str(int(root_key))
        if not scope.selected_contest(chat, root):
            return "protected"
        valid = (
            sk == f"CHAT#{chat}#ROOT#{int(root):013d}"
            and row.get("kind") == "contest_ttl_outbox"
            and _positive_number(row.get("expires_at"))
            and _positive_number(row.get("created_at"))
            and "ttl" not in row
        )
        kind = "retired_contest_outbox"
    elif pk.startswith("CHAT#"):
        chat = pk.removeprefix("CHAT#")
        if not scope.selected_chat(chat):
            return "protected"
        match = re.fullmatch(r"CONTEST#([0-9]{13,20})#(META|PARTICIPANT#([0-9]{20}))", sk)
        if match:
            root = str(int(match[1]))
            if not scope.selected_contest(chat, root):
                return "protected"
            prefix = f"CONTEST#{int(root):013d}#"
            if match[2] == "META":
                valid = (
                    sk == prefix + "META"
                    and row.get("kind") == "contest"
                    and row.get("status")
                    in {"CREATING", "CREATION_FAILED", "OPEN", "DRAWING", "DRAWN", "CANCELLED", "ORPHANED"}
                    and _positive_number(row.get("created_at"))
                )
                kind = "retired_contest_meta"
            else:
                user = row.get("user_id")
                valid = (
                    isinstance(user, str)
                    and bool(POSITIVE_ID.fullmatch(user))
                    and sk == f"{prefix}PARTICIPANT#{int(user):020d}"
                    and row.get("kind") == "contest_participant"
                    and _positive_number(row.get("entry_message_id"))
                    and _positive_number(row.get("accepted_at"))
                    and isinstance(row.get("text"), str)
                )
                kind = "retired_contest_participant"
        elif re.fullmatch(r"CONTEST_RULE#[0-9]{13,20}", sk):
            root_value = row.get("root_message_id")
            if not _positive_number(root_value):
                return "protected"  # Its root cannot be attributed; never guess.
            root = str(int(root_value))
            if not scope.selected_contest(chat, root):
                return "protected"
            rules = row.get("rules_message_id")
            valid = (
                _positive_number(rules)
                and sk == f"CONTEST_RULE#{int(rules):013d}"
                and row.get("kind") == "contest_rule_anchor"
                and _positive_number(row.get("created_at"))
            )
            kind = "retired_contest_rule"
        else:
            return "protected"
    else:
        return "protected"
    if (
        not valid
        or row.get("chat_id") != chat
        or not _positive_number(row.get("root_message_id"))
        or int(row["root_message_id"]) != int(root)
    ):
        raise CleanupError("invalid_selected_retired_contest_record")
    return kind


def classify(scope, row):
    key = item_key(row)
    pk, sk = key["pk"], key["sk"]
    if pk == "CONTEST_TTL_OUTBOX" or sk.startswith(("CONTEST#", "CONTEST_RULE#")):
        return _retired_contest_kind(scope, row, pk, sk)
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
