"""Local operator interface. Without --execute even `apply` only verifies read state."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import time
from pathlib import Path

from .archive import RETENTION_SECONDS, expire, load_key, open_archive, seal, secure_directory
from .aws_adapter import AWSAdapter
from .engine import apply_cleanup, check_snapshot, make_backup, make_manifest, summary, validate_backup
from .policy import CleanupError, Scope, classify, digest

REPOSITORY = Path(__file__).resolve().parents[3]


def source_commit():
    """The executable tool and its locked imports must belong to the reviewed HEAD."""
    paths = ["dev/tools/legacy_cleanup", "dev/__init__.py", "dev/tools/__init__.py", "pyproject.toml", "uv.lock"]
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", *paths], cwd=REPOSITORY, text=True
    )
    if status:
        raise CleanupError("cleanup_source_or_dependencies_dirty")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise CleanupError("invalid_cleanup_source_commit")
    return commit


def _read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _key(args, directory):
    path = Path(args.key_file).resolve()
    if path == directory or directory in path.parents:
        raise CleanupError("key_must_be_separate_from_archive_directory")
    return load_key(args.key_file)


def _manifest(directory, key, now):
    return open_archive(directory / "manifest.zenc", key, now=now)[0]


def run(args, *, adapter_factory=AWSAdapter, clock=time.time):
    now = int(clock())
    directory = secure_directory(args.archive_dir, repository_root=REPOSITORY)
    key = _key(args, directory)
    current_commit = source_commit() if args.command in ("plan", "backup", "apply") else None
    if args.command == "archives":
        entries = []
        for name in ("manifest.zenc", "backup.zenc", "journal.zenc"):
            path = directory / name
            if path.exists():
                _, header = open_archive(path, key, now=now, allow_expired=True)
                entries.append({"name": name, **header, "expired": now >= header["expires_at"]})
        return {"cloud_mutations": False, "archives": entries, "physical_erasure_complete": False}
    if args.command == "expire":
        path = directory / args.archive_name
        if Path(args.archive_name).name != args.archive_name or not args.archive_name.endswith(".zenc"):
            raise CleanupError("invalid_archive_filename")
        return expire(path, key, now=now, expected_digest=args.expected_digest, apply=args.execute)
    if args.command == "plan":
        scope = Scope.from_dict(_read_json(args.scope))
        adapter = adapter_factory(scope)
        manifest = make_manifest(scope, adapter.snapshot(scope), now=now, source_commit=current_commit)
        seal(directory, "manifest.zenc", manifest, key, now=now)
        return {
            **summary(manifest),
            "cloud_mutations": False,
            "backup_created": False,
            "archives_expire_at": now + RETENTION_SECONDS,
        }
    manifest = _manifest(directory, key, now)
    if current_commit is not None and manifest["source_commit"] != current_commit:
        raise CleanupError("cleanup_source_commit_changed_since_manifest")
    scope = Scope.from_dict(manifest["scope"])
    adapter = adapter_factory(scope)
    deadline = manifest["created_at"] + RETENTION_SECONDS
    if args.command == "backup":
        backup = make_backup(manifest, adapter.snapshot(scope))
        seal(directory, "backup.zenc", backup, key, now=now, expires_at=deadline)
        return {
            **summary(manifest),
            "backup_created": True,
            "backup_content_sha256": digest(backup),
            "cloud_mutations": False,
            "archives_expire_at": deadline,
        }
    if args.command == "status":
        snapshot = adapter.snapshot(scope)
        check_snapshot(manifest, snapshot, resume=True)
        return {
            **summary(manifest),
            "cloud_mutations": False,
            "remaining_table_targets": sum(classify(scope, row) != "protected" for row in snapshot["rows"]),
            "remaining_vectors": sum(len(rows) for rows in snapshot["vectors"].values()),
            "physical_erasure_complete": False,
        }
    backup, header = open_archive(directory / "backup.zenc", key, now=now)
    validate_backup(manifest, backup)
    if header["expires_at"] != deadline or args.expected_digest != digest(manifest):
        raise CleanupError("explicit_manifest_or_backup_deadline_mismatch")
    evidence = _read_json(args.evidence)
    adapter.verify_gate(scope, manifest, evidence)
    check_snapshot(manifest, adapter.snapshot(scope), resume=True)
    if not args.execute:
        return {
            **summary(manifest),
            "readiness_verified": True,
            "cloud_mutations": False,
            "physical_erasure_complete": False,
        }
    journal_path = directory / "journal.zenc"
    journal = (
        open_archive(journal_path, key, now=now)[0]
        if journal_path.exists()
        else {"manifest_sha256": digest(manifest), "state": "prepared"}
    )

    def save(value):
        seal(directory, "journal.zenc", value, key, now=int(clock()), expires_at=deadline, replace=True)

    return apply_cleanup(
        adapter,
        manifest,
        backup,
        expected_digest=args.expected_digest,
        evidence=evidence,
        journal=journal,
        save_journal=save,
    )


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("command", choices=("plan", "backup", "apply", "status", "archives", "expire"))
    result.add_argument("--archive-dir", required=True)
    result.add_argument("--key-file", required=True, help="Separate owner-only 32-byte encryption key file")
    result.add_argument("--scope", help="Explicit account/region/table/index/chat scope JSON; plan only")
    result.add_argument("--expected-digest", help="Exact decrypted manifest digest; expiry uses archive content digest")
    result.add_argument("--evidence", help="Reviewed stop/drain evidence JSON; apply only")
    result.add_argument("--archive-name", help="One authenticated archive to expire")
    result.add_argument("--execute", action="store_true", help="Explicit deletion; apply/expire only")
    return result


def _run_main(argv=None):
    args = parser().parse_args(argv)
    try:
        if (
            (args.command == "plan" and not args.scope)
            or (args.command == "apply" and (not args.evidence or not args.expected_digest))
            or (args.command == "expire" and (not args.archive_name or not args.expected_digest))
            or (args.execute and args.command not in ("apply", "expire"))
        ):
            raise CleanupError("missing_or_conflicting_command_arguments")
        output = run(args)
    except CleanupError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2
    except Exception as exc:
        # Deliberately never emit exception text/chain: AWS may echo values or credentials.
        print(json.dumps({"ok": False, "error": "operation_failed", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({"ok": True, **output}, sort_keys=True))
    return 0


def main(argv=None):
    # SDK debug logging can include raw records; suppress it only during this CLI call.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        return _run_main(argv)
    finally:
        logging.disable(previous)


if __name__ == "__main__":
    raise SystemExit(main())
