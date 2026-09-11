"""Manifest-bound deletion; every cloud mutation follows a fresh cutover gate."""

from __future__ import annotations

from collections import Counter

from .archive import RETENTION_SECONDS
from .policy import CleanupError, Scope, classify, digest, item_key

FORMAT = "zerde-legacy-cleanup-manifest-v1"


def table_entries(scope, rows):
    entries = []
    seen = set()
    for row in rows:
        key = item_key(row)
        identity = (key["pk"], key["sk"])
        if identity in seen:
            raise CleanupError("duplicate_table_key_during_scan")
        seen.add(identity)
        entries.append({"key": key, "kind": classify(scope, row), "sha256": digest(row)})
    return sorted(entries, key=lambda item: (item["key"]["pk"], item["key"]["sk"]))


def vector_entries(vectors):
    result = []
    for arn, rows in sorted(vectors.items()):
        seen = set()
        for row in rows:
            key = row.get("key")
            if not isinstance(key, str) or not key or key in seen or "data" not in row:
                raise CleanupError("invalid_or_duplicate_vector_snapshot")
            seen.add(key)
            result.append({"index_arn": arn, "key": key, "sha256": digest(row)})
    return sorted(result, key=lambda item: (item["index_arn"], item["key"]))


def protected_digest(entries):
    return digest([entry for entry in entries if entry["kind"] == "protected"])


def make_manifest(scope, snapshot, *, now, source_commit):
    if snapshot["identity"]["account_id"] != scope.account_id or snapshot["identity"]["region"] != scope.region:
        raise CleanupError("account_or_region_mismatch")
    if set(snapshot["vectors"]) != set(scope.index_arns):
        raise CleanupError("index_inventory_mismatch")
    entries = table_entries(scope, snapshot["rows"])
    return {
        "format": FORMAT,
        "created_at": now,
        "source_commit": source_commit,
        "scope": scope.as_dict(),
        "identity": snapshot["identity"],
        "table_entries": entries,
        "vector_entries": vector_entries(snapshot["vectors"]),
        "protected_count": sum(entry["kind"] == "protected" for entry in entries),
        "protected_sha256": protected_digest(entries),
    }


def summary(manifest):
    """Public-safe output: no row keys, identities, text, vector metadata or secrets."""
    return {
        "manifest_sha256": digest(manifest),
        "created_at": manifest["created_at"],
        "type_counts": dict(Counter(entry["kind"] for entry in manifest["table_entries"])),
        "vector_count": len(manifest["vector_entries"]),
        "protected_count": manifest["protected_count"],
        "protected_sha256": manifest["protected_sha256"],
    }


def check_snapshot(manifest, snapshot, *, resume=False):
    scope = Scope.from_dict(manifest["scope"])
    if manifest.get("format") != FORMAT or snapshot["identity"] != manifest["identity"]:
        raise CleanupError("resource_identity_changed")
    rows = table_entries(scope, snapshot["rows"])
    if (
        protected_digest(rows) != manifest["protected_sha256"]
        or sum(row["kind"] == "protected" for row in rows) != manifest["protected_count"]
    ):
        raise CleanupError("protected_business_data_changed")
    expected_rows = {(row["key"]["pk"], row["key"]["sk"]): row for row in manifest["table_entries"]}
    current_rows = {(row["key"]["pk"], row["key"]["sk"]): row for row in rows}
    expected_vectors = {(row["index_arn"], row["key"]): row for row in manifest["vector_entries"]}
    current_vectors = {(row["index_arn"], row["key"]): row for row in vector_entries(snapshot["vectors"])}
    if set(snapshot["vectors"]) != set(scope.index_arns):
        raise CleanupError("index_inventory_changed")
    for current, expected in ((current_rows, expected_rows), (current_vectors, expected_vectors)):
        if any(key not in expected or expected[key] != row for key, row in current.items()):
            raise CleanupError("manifest_content_changed")
        if not resume and current != expected:
            raise CleanupError("manifest_content_changed")
    return scope


def make_backup(manifest, snapshot):
    scope = check_snapshot(manifest, snapshot)
    return {
        "format": "zerde-legacy-cleanup-backup-v1",
        "manifest_sha256": digest(manifest),
        "identity": snapshot["identity"],
        "expires_at": manifest["created_at"] + RETENTION_SECONDS,
        "rows": [row for row in snapshot["rows"] if classify(scope, row) != "protected"],
        "vectors": snapshot["vectors"],
        "restore_policy": "offline_review_only_never_restore_to_enabled_memory",
    }


def validate_backup(manifest, backup):
    scope = Scope.from_dict(manifest["scope"])
    if (
        backup.get("format") != "zerde-legacy-cleanup-backup-v1"
        or backup.get("manifest_sha256") != digest(manifest)
        or backup.get("identity") != manifest["identity"]
        or backup.get("expires_at") != manifest["created_at"] + RETENTION_SECONDS
    ):
        raise CleanupError("backup_manifest_mismatch")
    expected = [row for row in manifest["table_entries"] if row["kind"] != "protected"]
    if (
        table_entries(scope, backup["rows"]) != expected
        or vector_entries(backup["vectors"]) != manifest["vector_entries"]
    ):
        raise CleanupError("backup_incomplete_or_changed")
    if set(backup["vectors"]) != set(scope.index_arns):
        raise CleanupError("backup_index_inventory_mismatch")


def apply_cleanup(adapter, manifest, backup, *, expected_digest, evidence, journal, save_journal):
    """Resume only this manifest. Missing exact keys are safe after an ambiguous delete.

    The journal records progress; it never grants wider scope. Conditions compare every
    known original attribute, not a fictitious atomic whole-row hash. All writers must
    therefore be stopped and drained before the first delete and throughout this run.
    """
    if expected_digest != digest(manifest):
        raise CleanupError("explicit_manifest_digest_mismatch")
    validate_backup(manifest, backup)
    if journal.get("manifest_sha256") != expected_digest:
        raise CleanupError("journal_manifest_mismatch")
    scope = Scope.from_dict(manifest["scope"])

    def remaining_window():
        if int(adapter.clock()) + 30 >= backup["expires_at"]:
            raise CleanupError("backup_expired_or_insufficient_send_window")
        if int(adapter.clock()) + 30 >= evidence.get("valid_until", 0):
            raise CleanupError("cutover_evidence_expired_or_insufficient_send_window")

    def gate():
        remaining_window()
        adapter.verify_gate(scope, manifest, evidence)
        remaining_window()

    gate()
    check_snapshot(manifest, adapter.snapshot(scope), resume=True)
    # Validate all conditions before any deletion: very wide items require manual review.
    for row in backup["rows"]:
        adapter.validate_delete_condition(row)
    journal["state"] = "deleting"
    save_journal(journal)
    vectors = {(arn, row["key"]): row for arn, rows in backup["vectors"].items() for row in rows}
    for arn in scope.index_arns:
        expected = [entry for entry in manifest["vector_entries"] if entry["index_arn"] == arn]
        for offset in range(0, len(expected), 25):
            gate()
            chunk = expected[offset : offset + 25]
            present = adapter.get_vectors(arn, [entry["key"] for entry in chunk])
            selected = []
            for key, row in present.items():
                original = vectors.get((arn, key))
                if original is None or digest(row) != digest(original):
                    raise CleanupError("vector_changed_before_delete")
                selected.append(key)
            if selected:
                remaining_window()
                adapter.delete_vectors(arn, selected)
                if adapter.get_vectors(arn, selected):
                    raise CleanupError("vector_delete_not_confirmed")
            journal["vector_batches_confirmed"] = journal.get("vector_batches_confirmed", 0) + 1
            save_journal(journal)
    # Markers are removed only after all explicitly selected old indexes are empty.
    if any(adapter.list_vectors(arn) for arn in scope.index_arns):
        raise CleanupError("legacy_vectors_remain_or_were_recreated")
    # Retired contest recovery markers go last, after every selected contest row.
    # Complete writer/replay retirement remains mandatory throughout deletion.
    rows = sorted(
        backup["rows"],
        key=lambda row: (
            {"vector_marker": 1, "retired_contest_outbox": 2}.get(classify(scope, row), 0),
            row["pk"],
            row["sk"],
        ),
    )
    for offset in range(0, len(rows), 25):
        gate()
        for original in rows[offset : offset + 25]:
            current = adapter.get_item(item_key(original))
            if current is None:
                continue
            if digest(current) != digest(original):
                raise CleanupError("item_changed_before_delete")
            remaining_window()
            adapter.delete_item(original)
            if adapter.get_item(item_key(original)) is not None:
                raise CleanupError("item_delete_not_confirmed")
        journal["table_batches_confirmed"] = journal.get("table_batches_confirmed", 0) + 1
        save_journal(journal)
    gate()
    final = adapter.snapshot(scope)
    check_snapshot(manifest, final, resume=True)
    gate()
    if any(classify(scope, row) != "protected" for row in final["rows"]) or any(final["vectors"].values()):
        raise CleanupError("legacy_online_data_remains")
    journal["state"] = "online_clean_copies_pending"
    save_journal(journal)
    return {
        **summary(manifest),
        "online_clean": True,
        "physical_erasure_complete": False,
        "copies_pending": ["local_encrypted_archives", "logs", "pitr_and_backups", "queue_and_dlq_bodies"],
        "protected_business_data_verified": True,
        "retention_expectations": {
            "local_archives_delete_by": backup["expires_at"],
            "queue_retention_from_stop_until": max(
                evidence["stopped_at"] + int(queue["retention_seconds"]) for queue in evidence["queues"]
            ),
            "logs_and_pitr_and_backups": "separate_inventory_and_physical_readback_required",
        },
    }
