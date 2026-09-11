"""Local durable evaluation records; never production/AWS accounting."""

import fcntl
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .contract import EvaluationInputError, fingerprint


class SessionError(EvaluationInputError):
    pass


def atomic_json(path, document):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(document, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def exclusive_lock(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SessionError("Another evaluation owns this directory") from None
        yield
    finally:
        os.close(fd)


def initialise_session(directory, manifest, *, resume):
    path = directory / "session.json"
    if path.exists():
        if not resume:
            raise SessionError("Existing evaluation requires --resume")
        if json.loads(path.read_text()) != manifest:
            raise SessionError("Evaluation configuration or executable input changed")
    elif resume:
        raise SessionError("No evaluation manifest to resume")
    else:
        if set(p.name for p in directory.iterdir()) - {"session.lock"}:
            raise SessionError("New evaluation requires an empty directory")
        atomic_json(path, manifest)


class AttemptLedger:
    """One SQLite transaction before each possible wire attempt; unknowns retain cost.

    The caller holds provider.lock for this object's lifetime. Logical keys exclude
    the request hash deliberately: changed input at an existing ordinal is drift,
    not permission to issue a new billed request.
    """

    def __init__(self, directory, manifest, *, clock=time.time):
        from services.memory_budget import MODEL, PRICE_VERSION, RESERVATION_MICRO_USD

        if manifest["model"] != MODEL or manifest["price_version"] != PRICE_VERSION:
            raise SessionError("Unpriced evaluation model")
        self.manifest, self.clock = manifest, clock
        self.reservation = RESERVATION_MICRO_USD
        path = Path(directory) / "attempts.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS attempts ("
            "logical_id TEXT PRIMARY KEY, scenario_id TEXT NOT NULL, kind TEXT NOT NULL, ordinal INTEGER NOT NULL, "
            "request_sha256 TEXT NOT NULL, request_json TEXT NOT NULL, state TEXT NOT NULL, "
            "charged_micro_usd INTEGER NOT NULL, started_at REAL NOT NULL, finished_at REAL, "
            "response_json TEXT, evidence_json TEXT, hits INTEGER NOT NULL DEFAULT 0)"
        )
        old = self.db.execute("SELECT fingerprint FROM config WHERE id=1").fetchone()
        if old and old[0] != fingerprint(manifest):
            self.db.close()
            raise SessionError("Persistent provider configuration changed")
        self.db.execute("INSERT OR IGNORE INTO config VALUES (1, ?)", (fingerprint(manifest),))
        self.db.commit()

    def close(self):
        self.db.close()

    @staticmethod
    def identity(call):
        if (
            not isinstance(call, dict)
            or set(call) != {"scenario_id", "kind", "ordinal", "request"}
            or not isinstance(call["scenario_id"], str)
            or call["kind"] not in {"extraction", "answer"}
            or type(call["ordinal"]) is not int
            or call["ordinal"] < 0
            or not isinstance(call["request"], dict)
        ):
            raise SessionError("Invalid provider call envelope")
        return fingerprint({key: call[key] for key in ("scenario_id", "kind", "ordinal")})

    def cached(self, call):
        key = self.identity(call)
        if call["scenario_id"] not in self.manifest["scenario_ids"]:
            raise SessionError("Provider call is outside the planned scenarios")
        row = self.db.execute("SELECT * FROM attempts WHERE logical_id=?", (key,)).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != fingerprint(call["request"]):
            raise SessionError("Provider request changed at a recorded logical ordinal")
        if fingerprint(json.loads(row["request_json"])) != row["request_sha256"]:
            raise SessionError("Recorded request failed its checksum")
        with self.db:
            self.db.execute("UPDATE attempts SET hits=hits+1 WHERE logical_id=?", (key,))
        if row["state"] == "RESPONSE":
            payload = json.loads(row["response_json"])
            if fingerprint(payload) != json.loads(row["evidence_json"])["payload_sha256"]:
                raise SessionError("Recorded response failed its checksum")
            return {"ok": True, "payload": payload, "cache_hit": True}
        return {"ok": False, "reason": "recorded_unknown", "cache_hit": True}

    def pacing_delay(self):
        row = self.db.execute("SELECT MAX(started_at) FROM attempts").fetchone()
        return max(0.0, (row[0] or 0) + 60 / self.manifest["rpm"] - self.clock())

    def reserve(self, call):
        key = self.identity(call)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.check_available()
            self.db.execute(
                "INSERT INTO attempts (logical_id,scenario_id,kind,ordinal,request_sha256,request_json,state,"
                "charged_micro_usd,started_at) VALUES (?,?,?,?,?,?,'INFLIGHT',?,?)",
                (
                    key,
                    call["scenario_id"],
                    call["kind"],
                    call["ordinal"],
                    fingerprint(call["request"]),
                    json.dumps(call["request"], ensure_ascii=False, allow_nan=False),
                    self.reservation,
                    self.clock(),
                ),
            )
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        return key

    def check_available(self):
        if self.db.execute("SELECT 1 FROM attempts WHERE state='ACCOUNTING_ERROR' LIMIT 1").fetchone():
            raise SessionError("accounting_blocked")
        count, total = self.db.execute("SELECT COUNT(*), COALESCE(SUM(charged_micro_usd), 0) FROM attempts").fetchone()
        if count >= self.manifest["max_calls"]:
            raise SessionError("max_calls_exhausted")
        if total + self.reservation > self.manifest["budget_micro_usd"]:
            raise SessionError("budget_exhausted")

    def finish(self, key, payload, evidence):
        from services.memory_budget import MemoryBudgetRepository

        charge, usage_verified, anomaly = self.reservation, False, False
        if isinstance(payload, dict):
            try:
                actual = MemoryBudgetRepository._usage_cost(payload.get("usageMetadata"))
            except (KeyError, TypeError, ValueError):
                pass  # Missing/unpriced usage cannot authorize a refund.
            else:
                charge, usage_verified = actual, True
                anomaly = actual > self.reservation
        evidence = {
            **evidence,
            "usage_verified": usage_verified,
            "usage_anomaly": anomaly,
            "payload_sha256": fingerprint(payload) if payload is not None else None,
        }
        with self.db:
            cursor = self.db.execute(
                "UPDATE attempts SET state=?,charged_micro_usd=?,finished_at=?,response_json=?,evidence_json=? "
                "WHERE logical_id=? AND state='INFLIGHT'",
                (
                    "ACCOUNTING_ERROR" if anomaly else "RESPONSE" if isinstance(payload, dict) else "UNKNOWN",
                    charge,
                    self.clock(),
                    json.dumps(payload, ensure_ascii=False, allow_nan=False) if payload is not None else None,
                    json.dumps(evidence, ensure_ascii=False, allow_nan=False),
                    key,
                ),
            )
            if cursor.rowcount != 1:
                raise SessionError("Attempt settlement is not an active reservation")
        return not anomaly

    def summary(self, *, scenario_id=None):
        rows = self.db.execute(
            "SELECT * FROM attempts" + (" WHERE scenario_id=?" if scenario_id else ""),
            (scenario_id,) if scenario_id else (),
        ).fetchall()
        return {
            "evidence_kind": "local_real_provider_budget_not_aws_or_moto",
            "attempts_reserved": len(rows),
            "charged_upper_micro_usd": sum(row["charged_micro_usd"] for row in rows),
            "cache_hits": sum(row["hits"] for row in rows),
            "responses": sum(row["state"] == "RESPONSE" for row in rows),
            "unknown_attempts": sum(row["state"] != "RESPONSE" for row in rows),
            "usage_verified_attempts": sum(
                bool(json.loads(row["evidence_json"] or "{}").get("usage_verified")) for row in rows
            ),
        }
