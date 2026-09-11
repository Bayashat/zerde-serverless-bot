"""Offline cleanup rehearsal. Moto DDB conditions plus a paged fake vector owner."""

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from dev.tools.legacy_cleanup import archive, cli
from dev.tools.legacy_cleanup.aws_adapter import ATTESTATIONS, CONTEST_ATTESTATIONS, AWSAdapter
from dev.tools.legacy_cleanup.engine import apply_cleanup, make_backup, make_manifest, summary, validate_backup
from dev.tools.legacy_cleanup.policy import CleanupError, RetiredContest, Scope, canonical, classify, digest, untagged

ACCOUNT = "123456789012"
REGION = "eu-central-1"
TABLE = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/legacy-memory"
INDEX = f"arn:aws:s3vectors:{REGION}:{ACCOUNT}:bucket/legacy-bucket/index/old-memory"
NOW = 2_000_000_000


def scope(**changes):
    return Scope(
        **{
            "account_id": ACCOUNT,
            "region": REGION,
            "table_arn": TABLE,
            "index_arns": (INDEX,),
            "chat_ids": None,
            **changes,
        }
    )


def marker():
    return {
        "pk": "MEMORY_VECTOR_DELETE#-100",
        "sk": "USER_FACT#old",
        "chat_id": "-100",
        "generation": "deletion-generation",
        "vector_key": "memory/" + hashlib.sha256(b"-100:USER_FACT#old").hexdigest(),
    }


class FakeVectors:
    def __init__(self):
        self.rows = {
            "orphan": {
                "key": "orphan",
                "data": {"float32": [0.25, 1.0]},
                "metadata": {"old_body": "private imported text"},
            }
        }
        self.deleted = []
        self.index = {"indexArn": INDEX, "creationTime": NOW - 10_000, "dataType": "float32", "dimension": 2}

    def get_index(self, **kwargs):
        assert kwargs == {"indexArn": INDEX}
        return {"index": self.index.copy()}

    def list_vectors(self, **kwargs):
        assert kwargs["returnData"] and kwargs["returnMetadata"]
        return {"vectors": copy.deepcopy(list(self.rows.values()))}

    def get_vectors(self, **kwargs):
        return {"vectors": copy.deepcopy([self.rows[key] for key in kwargs["keys"] if key in self.rows])}

    def delete_vectors(self, **kwargs):
        self.deleted.extend(kwargs["keys"])
        for key in kwargs["keys"]:
            self.rows.pop(key, None)
        return {}


@pytest.fixture
def adapter():
    with mock_aws():
        obj = AWSAdapter.__new__(AWSAdapter)
        obj.scope = scope()
        obj.now = NOW
        obj.clock = lambda: obj.now
        obj.ddb = boto3.resource("dynamodb", region_name=REGION)
        obj.table = obj.ddb.create_table(
            TableName="legacy-memory",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
        )
        obj.sts = boto3.client("sts", region_name=REGION)
        obj.vectors = FakeVectors()
        obj.functions, obj.events, obj.queues = MagicMock(), MagicMock(), MagicMock()
        obj.functions.list_aliases.return_value = {"Aliases": []}
        obj.functions.list_event_source_mappings.return_value = {"EventSourceMappings": []}
        obj.functions.get_function_configuration.side_effect = lambda FunctionName: {
            "FunctionArn": FunctionName,
            "RevisionId": "revision",
            "CodeSha256": "reviewed-code",
            "State": "Active",
            "LastUpdateStatus": "Successful",
            "Timeout": 900,
            "LastModified": "2020-01-01T00:00:00Z",
        }
        obj.queues.get_queue_attributes.return_value = {
            "Attributes": {
                "QueueArn": f"arn:aws:sqs:{REGION}:{ACCOUNT}:mixed-main",
                "MessageRetentionPeriod": "86400",
                "VisibilityTimeout": "960",
                "ApproximateNumberOfMessagesNotVisible": "2",
            }
        }
        for row in [
            {
                "pk": "CHAT#-100",
                "sk": "MSG#1",
                "text": "private imported text",
                "n": Decimal("1.25"),
                "tags": {"a", "b"},
            },
            {"pk": "CHAT#-100", "sk": "AGENT_REPLY#1", "text": "old generated profile"},
            {"pk": "CHAT#-100", "sk": "SETTINGS", "enabled": False},
            {"pk": "CHAT#-100", "sk": "CONTEST#1", "winner": "protected"},
            {"pk": "CONTEST_TTL_OUTBOX", "sk": "-100#1", "active": True},
            {"pk": "CHAT#-100", "sk": "UNKNOWN#1", "private": "protected"},
            {"pk": "CHAT#-100", "sk": "BOT_COMMITMENT#1", "text": "needs independent confirmation"},
            marker(),
        ]:
            obj.table.put_item(Item=row)
        yield obj


def prepared(adapter):
    snapshot = adapter.snapshot(adapter.scope)
    manifest = make_manifest(adapter.scope, snapshot, now=NOW, source_commit="a" * 40)
    return manifest, make_backup(manifest, snapshot)


def evidence(manifest):
    return {
        "format": "zerde-legacy-cutover-evidence-v1",
        "manifest_sha256": digest(manifest),
        "reviewed_evidence_sha256": "b" * 64,
        "observed_at": NOW,
        "valid_until": NOW + 900,
        "stopped_at": NOW - 1000,
        "old_max_timeout_seconds": 900,
        **{key: True for key in ATTESTATIONS},
        **(
            {**{key: True for key in CONTEST_ATTESTATIONS}, "retired_contest_recovery_rules": []}
            if manifest["scope"].get("retired_contests")
            else {}
        ),
        "lambda_targets": [
            {
                "role": role,
                "function_arn": f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{role}",
                "revision_id": "revision",
                "code_sha256": "reviewed-code",
                "aliases": [],
                "event_sources": [],
            }
            for role in ("bot", "vector_indexer")
        ],
        "disabled_legacy_rules": [],
        "queues": [
            {
                "url": "https://sqs.eu-central-1.amazonaws.com/123456789012/mixed-main",
                "arn": f"arn:aws:sqs:{REGION}:{ACCOUNT}:mixed-main",
                "retention_seconds": 86400,
                "visibility_timeout_seconds": 960,
                "dedicated_legacy": False,
            }
        ],
    }


def execute(adapter, manifest, backup, *, proof=None, save=None):
    return apply_cleanup(
        adapter,
        manifest,
        backup,
        expected_digest=digest(manifest),
        evidence=proof or evidence(manifest),
        journal={"manifest_sha256": digest(manifest)},
        save_journal=save or (lambda value: None),
    )


def test_moto_full_cleanup_preserves_business_and_removes_orphan_before_marker(adapter):
    manifest, backup = prepared(adapter)
    result = execute(adapter, manifest, backup)
    assert result["online_clean"] and not result["physical_erasure_complete"]
    assert result["protected_business_data_verified"]
    rows = adapter.scan_rows()
    assert len(rows) == 5 and all(classify(adapter.scope, row) == "protected" for row in rows)
    assert adapter.vectors.deleted == ["orphan"]
    assert "private imported text" not in json.dumps(summary(manifest))
    assert not adapter.queues.mock_calls[0][0].startswith(("delete", "purge", "receive"))


@pytest.mark.parametrize("key", ATTESTATIONS)
def test_each_missing_stop_attestation_prevents_all_mutations(adapter, key):
    manifest, backup = prepared(adapter)
    proof = evidence(manifest)
    proof[key] = False
    with pytest.raises(CleanupError, match="incomplete_reviewed_stop_evidence"):
        execute(adapter, manifest, backup, proof=proof)
    assert len(adapter.scan_rows()) == 8 and not adapter.vectors.deleted


@pytest.mark.parametrize(
    "change,code",
    [
        ({"valid_until": NOW}, "insufficient_send_window"),
        ({"stopped_at": NOW - 30}, "not_drained"),
        ({"old_max_timeout_seconds": 300}, "not_drained"),
        ({"lambda_targets": []}, "incomplete_lambda"),
        ({"queues": []}, "retention_inventory"),
    ],
)
def test_gate_requires_fresh_drain_and_complete_inventories(adapter, change, code):
    manifest, backup = prepared(adapter)
    proof = {**evidence(manifest), **change}
    with pytest.raises(CleanupError, match=code):
        execute(adapter, manifest, backup, proof=proof)
    assert not adapter.vectors.deleted


def test_changed_live_artifact_blocks_cleanup(adapter):
    manifest, backup = prepared(adapter)
    proof = evidence(manifest)
    proof["lambda_targets"][0]["revision_id"] = "stale"
    with pytest.raises(CleanupError, match="artifact_or_revision_changed"):
        execute(adapter, manifest, backup, proof=proof)
    assert not adapter.vectors.deleted


def test_wrong_account_and_recreated_index_cannot_apply(adapter):
    manifest, backup = prepared(adapter)
    adapter.vectors.index["creationTime"] += 1
    with pytest.raises(CleanupError, match="resource_identity_changed"):
        execute(adapter, manifest, backup)
    adapter.sts = MagicMock()
    adapter.sts.get_caller_identity.return_value = {"Account": "000000000000"}
    with pytest.raises(CleanupError, match="account_or_scope_mismatch"):
        adapter.identity(adapter.scope)


@pytest.mark.parametrize("sk", ["MSG#1", "SETTINGS", "NEW_TYPE#1"])
def test_changed_target_protected_or_unknown_new_row_stops_before_delete(adapter, sk):
    manifest, backup = prepared(adapter)
    adapter.table.put_item(Item={"pk": "CHAT#-100", "sk": sk, "unexpected": "concurrent write"})
    with pytest.raises(CleanupError, match="changed"):
        execute(adapter, manifest, backup)
    assert not adapter.vectors.deleted


def test_actual_native_ddb_condition_rejects_race_after_read(adapter):
    original = adapter.get_item({"pk": "CHAT#-100", "sk": "MSG#1"})
    adapter.table.update_item(
        Key={"pk": original["pk"], "sk": original["sk"]},
        UpdateExpression="SET #t = :t",
        ExpressionAttributeNames={"#t": "text"},
        ExpressionAttributeValues={":t": "changed"},
    )
    with pytest.raises(ClientError) as caught:
        adapter.delete_item(original)
    assert caught.value.response["Error"]["Code"] == "ConditionalCheckFailedException"
    assert adapter.get_item({"pk": original["pk"], "sk": original["sk"]})["text"] == "changed"


def test_unknown_attribute_addition_is_not_falsely_claimed_atomic_hash(adapter):
    original = adapter.get_item({"pk": "CHAT#-100", "sk": "MSG#1"})
    adapter.table.update_item(
        Key={"pk": original["pk"], "sk": original["sk"]},
        UpdateExpression="SET new_attribute = :v",
        ExpressionAttributeValues={":v": "new"},
    )
    # Document the real AWS limitation: complete writer-stop evidence remains mandatory.
    adapter.delete_item(original)
    assert adapter.get_item({"pk": original["pk"], "sk": original["sk"]}) is None


def test_crash_after_cloud_delete_before_journal_resumes_exact_manifest(adapter):
    manifest, backup = prepared(adapter)
    saved = []

    def save(value):
        saved.append(copy.deepcopy(value))
        if value.get("vector_batches_confirmed"):
            raise OSError("synthetic disk full")

    with pytest.raises(OSError):
        execute(adapter, manifest, backup, save=save)
    assert not adapter.vectors.rows and adapter.get_item({"pk": marker()["pk"], "sk": marker()["sk"]})
    assert execute(adapter, manifest, backup)["online_clean"]
    assert len(adapter.scan_rows()) == 5


def test_deleted_vectors_recreated_before_marker_stop(adapter):
    manifest, backup = prepared(adapter)
    original = adapter.list_vectors
    count = 0

    def list_vectors(arn):
        nonlocal count
        count += 1
        if count == 2:
            adapter.vectors.rows["recreated"] = {"key": "recreated", "data": {"float32": [0.0, 1.0]}, "metadata": {}}
        return original(arn)

    adapter.list_vectors = list_vectors
    with pytest.raises(CleanupError, match="legacy_vectors_remain"):
        execute(adapter, manifest, backup)
    assert adapter.get_item({"pk": marker()["pk"], "sk": marker()["sk"]})


def test_backup_incomplete_and_expired_fail_before_cloud_mutation(adapter):
    manifest, backup = prepared(adapter)
    incomplete = {**backup, "rows": backup["rows"][:-1]}
    with pytest.raises(CleanupError, match="backup_incomplete"):
        execute(adapter, manifest, incomplete)
    adapter.now = backup["expires_at"]
    with pytest.raises(CleanupError, match="backup_expired"):
        execute(adapter, manifest, backup)
    assert not adapter.vectors.deleted


def test_slow_predelete_read_does_not_use_expired_gate(adapter):
    manifest, backup = prepared(adapter)
    original = adapter.get_vectors

    def slow(arn, keys):
        result = original(arn, keys)
        adapter.now += 880
        return result

    adapter.get_vectors = slow
    with pytest.raises(CleanupError, match="insufficient_send_window"):
        execute(adapter, manifest, backup)
    assert not adapter.vectors.deleted


def test_policy_scopes_markers_and_protects_business():
    selected = scope(chat_ids=("-100",), confirmed_bot_prefixes=("BOT_COMMITMENT#",))
    assert classify(selected, {"pk": "CHAT#-100", "sk": "BOT_COMMITMENT#1"}) == "BOT_COMMITMENT"
    assert classify(selected, {"pk": "CHAT#-200", "sk": "MSG#1"}) == "protected"
    for sk in ("SETTINGS", "CONTEST#1", "CONTEST_RULE#1", "TYPO#1"):
        assert classify(selected, {"pk": "CHAT#-100", "sk": sk}) == "protected"
    assert classify(selected, marker()) == "vector_marker"
    with pytest.raises(CleanupError, match="invalid_vector_delete_marker"):
        classify(selected, {**marker(), "generation": ""})
    with pytest.raises(CleanupError):
        scope(index_arns=())
    with pytest.raises(CleanupError):
        scope(table_arn=TABLE.replace(ACCOUNT, "000000000000"))


def test_encrypted_backup_roundtrip_permissions_deadline_and_authentication(tmp_path):
    directory = archive.secure_directory(tmp_path / "archive", repository_root=Path.cwd())
    key = b"x" * 32
    value = {
        "text": "private imported text",
        "number": Decimal("1.20"),
        "binary": b"secret",
        "set": {"a", "b"},
        "$decimal": "literal user key",
    }
    result = archive.seal(directory, "backup.zenc", value, key, now=NOW)
    path = Path(result["path"])
    assert path.stat().st_mode & 0o777 == 0o600
    assert b"private imported text" not in path.read_bytes()
    assert archive.open_archive(path, key, now=NOW)[0] == value
    assert untagged(json.loads(canonical(value))) == value
    with pytest.raises(CleanupError, match="authentication"):
        archive.open_archive(path, b"z" * 32, now=NOW)
    with pytest.raises(CleanupError, match="archive_expired"):
        archive.open_archive(path, key, now=NOW + archive.RETENTION_SECONDS)
    expiry = archive.expire(path, key, now=NOW + archive.RETENTION_SECONDS, expected_digest=digest(value))
    assert not expiry["removed"] and path.exists()
    assert archive.expire(path, key, now=NOW + archive.RETENTION_SECONDS, expected_digest=digest(value), apply=True)[
        "removed"
    ]
    assert not path.exists()


def test_archive_rejects_repository_public_paths_and_symlink_keys(tmp_path):
    with pytest.raises(CleanupError, match="outside_repository"):
        archive.secure_directory(Path.cwd() / "cleanup-data", repository_root=Path.cwd())
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(CleanupError, match="permissions"):
        archive.secure_directory(public, repository_root=Path.cwd())
    key = tmp_path / "key"
    key.write_bytes(b"x" * 32)
    key.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(key)
    assert archive.load_key(key) == b"x" * 32
    with pytest.raises(CleanupError):
        archive.load_key(alias)


def test_cli_apply_is_read_only_without_execute(adapter, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "source_commit", lambda: "a" * 40)
    manifest, backup = prepared(adapter)
    directory = archive.secure_directory(tmp_path / "archive", repository_root=Path.cwd())
    key_file = tmp_path / "key"
    key_file.write_bytes(b"x" * 32)
    key_file.chmod(0o600)
    archive.seal(directory, "manifest.zenc", manifest, b"x" * 32, now=NOW)
    archive.seal(directory, "backup.zenc", backup, b"x" * 32, now=NOW)
    proof = tmp_path / "evidence.json"
    proof.write_text(json.dumps(evidence(manifest)))
    args = SimpleNamespace(
        command="apply",
        archive_dir=str(directory),
        key_file=str(key_file),
        expected_digest=digest(manifest),
        evidence=str(proof),
        execute=False,
    )
    result = cli.run(args, adapter_factory=lambda _: adapter, clock=lambda: NOW)
    assert not result["cloud_mutations"] and len(adapter.scan_rows()) == 8 and not adapter.vectors.deleted


def test_cli_never_prints_sdk_error_text(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run", lambda args: (_ for _ in ()).throw(RuntimeError("token=secret private body")))
    assert cli.main(["status", "--archive-dir", "/tmp/unused", "--key-file", "/tmp/unused-key"]) == 2
    output = capsys.readouterr().out
    assert "RuntimeError" in output and "secret" not in output and "private body" not in output


def test_real_sdk_vector_pagination_includes_empty_pages_and_metadata(adapter):
    from botocore.stub import Stubber

    client = boto3.client("s3vectors", region_name=REGION)
    with Stubber(client) as stub:
        args = {"indexArn": INDEX, "maxResults": 500, "returnData": True, "returnMetadata": True}
        stub.add_response("list_vectors", {"vectors": [], "nextToken": "next"}, args)
        stub.add_response(
            "list_vectors",
            {"vectors": [{"key": "orphan", "data": {"float32": [0.25, 1.0]}}]},
            {**args, "nextToken": "next"},
        )
        adapter.vectors = client
        assert adapter.list_vectors(INDEX) == [{"key": "orphan", "data": {"float32": [0.25, 1.0]}, "metadata": {}}]
        stub.assert_no_pending_responses()


def test_table_pagination_crosses_empty_page_and_detects_cycles(adapter):
    adapter.table = MagicMock()
    cursor = {"pk": "CHAT#-100", "sk": "MSG#page"}
    adapter.table.scan.side_effect = [
        {"Items": [], "LastEvaluatedKey": cursor},
        {"Items": [{"pk": "CHAT#-100", "sk": "MSG#last"}]},
    ]
    assert len(adapter.scan_rows()) == 1
    assert adapter.table.scan.call_args.kwargs["ExclusiveStartKey"] == cursor
    adapter.table.scan.side_effect = [{"Items": [], "LastEvaluatedKey": cursor}] * 2
    with pytest.raises(CleanupError, match="pagination_cycle"):
        adapter.scan_rows()


def test_protected_change_during_cleanup_never_reports_success(adapter):
    manifest, backup = prepared(adapter)
    original = adapter.delete_item

    def mutate(row):
        original(row)
        adapter.table.put_item(Item={"pk": "CHAT#-100", "sk": "SETTINGS", "enabled": True})

    adapter.delete_item = mutate
    with pytest.raises(CleanupError, match="protected_business_data_changed"):
        execute(adapter, manifest, backup)


def test_gate_rejects_reenabled_rule_alias_or_dedicated_inflight(adapter):
    manifest, _ = prepared(adapter)
    proof = evidence(manifest)
    proof["disabled_legacy_rules"] = [{"name": "old-rule", "arn": f"arn:aws:events:{REGION}:{ACCOUNT}:rule/old-rule"}]
    adapter.events.describe_rule.return_value = {"Arn": proof["disabled_legacy_rules"][0]["arn"], "State": "ENABLED"}
    with pytest.raises(CleanupError, match="schedule_not_disabled"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    proof = evidence(manifest)
    proof["queues"][0]["dedicated_legacy"] = True
    with pytest.raises(CleanupError, match="queue_not_drained"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    adapter.functions.list_aliases.return_value = {
        "Aliases": [
            {"AliasArn": "alias", "FunctionVersion": "1", "RoutingConfig": {"AdditionalVersionWeights": {"2": 0.1}}}
        ]
    }
    with pytest.raises(CleanupError, match="weighted_alias"):
        adapter.verify_gate(adapter.scope, manifest, evidence(manifest))


def test_manifest_before_stop_and_late_live_readback_fail(adapter):
    manifest, _ = prepared(adapter)
    proof = evidence(manifest)
    manifest["created_at"] = proof["stopped_at"] - 1
    proof["manifest_sha256"] = digest(manifest)
    with pytest.raises(CleanupError, match="predates_complete_writer_stop"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    manifest, _ = prepared(adapter)
    proof = evidence(manifest)
    original = adapter.queues.get_queue_attributes.return_value

    def slow(**kwargs):
        adapter.now += 901
        return original

    adapter.queues.get_queue_attributes.side_effect = slow
    with pytest.raises(CleanupError, match="expired_during_readback"):
        adapter.verify_gate(adapter.scope, manifest, proof)


def test_known_marker_outside_scope_remains_protected():
    assert classify(scope(chat_ids=("-200",)), marker()) == "protected"
    bad = {**marker(), "chat_id": "-200"}
    with pytest.raises(CleanupError, match="invalid_vector_delete_marker"):
        classify(scope(), bad)


def test_cleaned_moto_data_stays_empty_after_real_retired_worker_replay(adapter):
    from services.memory_cutover import RETIRED_TASK_TYPES
    from services.sqs_task_router import process_sqs_event, process_vector_sqs_event

    manifest, backup = prepared(adapter)
    execute(adapter, manifest, backup)
    before = digest(adapter.scan_rows())
    bot = MagicMock()
    for task_type in (*sorted(RETIRED_TASK_TYPES), "PROCESS_GROUP_ASK"):
        event = {
            "Records": [
                {"body": json.dumps({"task_type": task_type, "chat_id": -100, "user_text": "old private export"})}
            ]
        }
        process_sqs_event(event, bot, MagicMock(), adapter)
        process_vector_sqs_event(event, adapter)
    assert not bot.mock_calls and digest(adapter.scan_rows()) == before and not adapter.vectors.rows


def test_cli_restores_logging_state_even_on_argument_error():
    import logging

    before = logging.root.manager.disable
    with pytest.raises(SystemExit):
        cli.main([])
    assert logging.root.manager.disable == before


def test_gate_requires_unqualified_bot_and_indexer_artifacts(adapter):
    manifest, _ = prepared(adapter)
    proof = evidence(manifest)
    for target in proof["lambda_targets"]:
        target["function_arn"] += ":1"
    with pytest.raises(CleanupError, match="incomplete_lambda_guard_inventory"):
        adapter.verify_gate(adapter.scope, manifest, proof)


def test_alias_versions_are_verified_and_base_inventory_is_not_narrowed(adapter):
    manifest, _ = prepared(adapter)
    proof = evidence(manifest)
    base = proof["lambda_targets"][0]["function_arn"]
    alias = {"AliasArn": base + ":prod", "FunctionVersion": "1", "RevisionId": "alias-revision", "RoutingConfig": None}
    mapping = {
        "UUID": "mapping",
        "EventSourceArn": proof["queues"][0]["arn"],
        "FunctionArn": base + ":prod",
        "State": "Enabled",
    }
    proof["lambda_targets"][0].update(aliases=[alias], event_sources=[mapping])
    version = {**proof["lambda_targets"][0], "function_arn": base + ":1", "role": "version"}
    proof["lambda_targets"].append(version)
    adapter.functions.list_aliases.side_effect = lambda FunctionName: {
        "Aliases": [alias] if FunctionName == base else []
    }
    adapter.functions.list_event_source_mappings.side_effect = lambda FunctionName: {
        "EventSourceMappings": [mapping] if FunctionName == base else []
    }
    adapter.verify_gate(adapter.scope, manifest, proof)
    assert all(call.kwargs["FunctionName"].count(":") == 6 for call in adapter.functions.list_aliases.call_args_list)
    proof["lambda_targets"].pop()
    with pytest.raises(CleanupError, match="unverified_alias_version"):
        adapter.verify_gate(adapter.scope, manifest, proof)


def test_dirty_or_staged_tool_or_dependency_cannot_claim_reviewed_commit(tmp_path, monkeypatch):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    package = repo / "dev/tools/legacy_cleanup"
    package.mkdir(parents=True)
    source = package / "engine.py"
    source.write_text("# reviewed\n")
    (repo / "uv.lock").write_text("# reviewed dependency\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "reviewed"],
        cwd=repo,
        check=True,
    )
    monkeypatch.setattr(cli, "REPOSITORY", repo)
    clean = cli.source_commit()
    assert len(clean) == 40
    source.write_text("# modified unreviewed\n")
    with pytest.raises(CleanupError, match="source_or_dependencies_dirty"):
        cli.source_commit()
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    with pytest.raises(CleanupError, match="source_or_dependencies_dirty"):
        cli.source_commit()
    subprocess.run(["git", "restore", "--staged", "--worktree", "."], cwd=repo, check=True)
    (repo / "uv.lock").write_text("# other dependencies\n")
    with pytest.raises(CleanupError, match="source_or_dependencies_dirty"):
        cli.source_commit()
    subprocess.run(["git", "restore", "."], cwd=repo, check=True)
    (package / "untracked.py").write_text("# shadow import\n")
    with pytest.raises(CleanupError, match="source_or_dependencies_dirty"):
        cli.source_commit()


def test_apply_different_head_refuses_before_aws_read(adapter, tmp_path, monkeypatch):
    manifest, _ = prepared(adapter)
    directory = archive.secure_directory(tmp_path / "archive", repository_root=Path.cwd())
    key_path = tmp_path / "key"
    key_path.write_bytes(b"x" * 32)
    key_path.chmod(0o600)
    archive.seal(directory, "manifest.zenc", manifest, b"x" * 32, now=NOW)
    monkeypatch.setattr(cli, "source_commit", lambda: "b" * 40)
    args = SimpleNamespace(command="apply", archive_dir=str(directory), key_file=str(key_path))
    with pytest.raises(CleanupError, match="source_commit_changed_since_manifest"):
        cli.run(args, adapter_factory=lambda _: pytest.fail("must not access AWS"), clock=lambda: NOW)


def contest_rows(chat="-100", root=10):
    """Historical writer wire shape, independent of the removed runtime package."""
    common = {"chat_id": chat, "root_message_id": root}
    pk, prefix = f"CHAT#{chat}", f"CONTEST#{root:013d}#"
    return [
        {
            **common,
            "pk": pk,
            "sk": prefix + "META",
            "kind": "contest",
            "status": "DRAWN",
            "created_at": NOW - 100,
            "winner_user_ids": ["77"],
            "winners": [{"user_id": "77", "text": "synthetic entry", "score": Decimal("1.25")}],
        },
        {
            **common,
            "pk": pk,
            "sk": prefix + f"PARTICIPANT#{77:020d}",
            "kind": "contest_participant",
            "user_id": "77",
            "entry_message_id": 100,
            "accepted_at": NOW - 90,
            "text": "synthetic entry",
        },
        {
            **common,
            "pk": pk,
            "sk": f"CONTEST_RULE#{root + 100:013d}",
            "kind": "contest_rule_anchor",
            "rules_message_id": root + 100,
            "created_at": NOW - 100,
        },
        {
            **common,
            "pk": "CONTEST_TTL_OUTBOX",
            "sk": f"CHAT#{chat}#ROOT#{root:013d}",
            "kind": "contest_ttl_outbox",
            "expires_at": NOW + 30 * 86400,
            "created_at": NOW - 10,
        },
    ]


def with_retired_contest(adapter):
    adapter.scope = scope(chat_ids=("-100",), retired_contests=(RetiredContest("-100", "10"),))
    for row in contest_rows():
        adapter.table.put_item(Item=row)
    return prepared(adapter)


def test_retirement_is_explicit_canonical_scope_and_old_scope_defaults_protect():
    original = scope().as_dict()
    original.pop("retired_contests")
    assert not Scope.from_dict(original).retired_contests
    assert all(classify(Scope.from_dict(original), row) == "protected" for row in contest_rows())
    explicit = {**original, "retired_contests": [{"chat_id": "-100", "root_message_id": "10"}]}
    selected = Scope.from_dict(explicit)
    assert Scope.from_dict(selected.as_dict()) == selected
    assert len({classify(selected, row) for row in contest_rows()}) == 4
    for bad in (
        True,
        ["CONTEST#"],
        [{"chat_id": "-100", "root_message_id": "010"}],
        [{"chat_id": "-100", "root_message_id": 10}],
        explicit["retired_contests"] * 2,
    ):
        with pytest.raises(CleanupError):
            Scope.from_dict({**original, "retired_contests": bad})
    with pytest.raises(CleanupError, match="out_of_scope"):
        Scope.from_dict({**explicit, "chat_ids": ["-200"]})


def test_moto_retirement_exact_roots_lossless_backup_and_outbox_last(adapter, tmp_path):
    manifest, backup = with_retired_contest(adapter)
    # A second root in the same chat, the same root in another chat, and unrelated
    # lifecycle/control/moderation/quiz data all remain protected.
    for row in [
        *contest_rows(root=11),
        *contest_rows(chat="-200"),
        {"pk": "CHAT#-100", "sk": "CONTEST#0000000000010#FUTURE", "kind": "unknown"},
        {"pk": "CHAT#-100", "sk": "CONTROL_COMMAND#one"},
        {"pk": "spam_case#-100", "sk": "10"},
        {"pk": "QUIZ#-100", "sk": "10"},
    ]:
        adapter.table.put_item(Item=row)
    manifest, backup = prepared(adapter)
    protected = {digest(row) for row in adapter.scan_rows() if classify(adapter.scope, row) == "protected"}
    assert sum(entry["kind"].startswith("retired_contest_") for entry in manifest["table_entries"]) == 4
    directory = archive.secure_directory(tmp_path / "retirement", repository_root=Path.cwd())
    archive.seal(directory, "backup.zenc", backup, b"r" * 32, now=NOW)
    restored, _ = archive.open_archive(directory / "backup.zenc", b"r" * 32, now=NOW)
    validate_backup(manifest, restored)
    assert {digest(row) for row in restored["rows"] if row.get("kind", "").startswith("contest")} == {
        digest(adapter.get_item({"pk": row["pk"], "sk": row["sk"]})) for row in contest_rows()
    }
    deleted, original_delete = [], adapter.delete_item

    def observe(row):
        deleted.append(classify(adapter.scope, row))
        if row.get("kind") == "contest_ttl_outbox":
            assert all(adapter.get_item({"pk": old["pk"], "sk": old["sk"]}) is None for old in contest_rows()[:-1])
        original_delete(row)

    adapter.delete_item = observe
    assert execute(adapter, manifest, restored)["online_clean"]
    assert deleted[-1] == "retired_contest_outbox"
    assert {digest(row) for row in adapter.scan_rows()} == protected


@pytest.mark.parametrize(
    "row_index,change",
    [
        (0, {"kind": "settings"}),
        (0, {"status": "UNREVIEWED"}),
        (0, {"chat_id": "-200"}),
        (0, {"root_message_id": 11}),
        (0, {"root_message_id": True}),
        (1, {"user_id": "78"}),
        (1, {"entry_message_id": Decimal("1.5")}),
        (2, {"rules_message_id": 111}),
        (2, {"kind": "other_business"}),
        (3, {"root_message_id": 11}),
        (3, {"chat_id": "-200"}),
        (3, {"ttl": NOW}),
    ],
)
def test_selected_contest_bad_shape_aborts_plan_before_mutation(adapter, row_index, change):
    with_retired_contest(adapter)
    row = {**contest_rows()[row_index], **change}
    adapter.table.put_item(Item=row)
    with pytest.raises(CleanupError, match="invalid_selected_retired_contest_record"):
        prepared(adapter)
    assert not adapter.vectors.deleted


def test_contest_orphans_are_scoped_without_requiring_expired_meta(adapter):
    with_retired_contest(adapter)
    meta = contest_rows()[0]
    adapter.table.delete_item(Key={"pk": meta["pk"], "sk": meta["sk"]})
    manifest, backup = prepared(adapter)
    assert sum(entry["kind"].startswith("retired_contest_") for entry in manifest["table_entries"]) == 3
    assert execute(adapter, manifest, backup)["online_clean"]


@pytest.mark.parametrize("attestation", CONTEST_ATTESTATIONS)
def test_contest_retirement_requires_specific_writer_and_replay_evidence(adapter, attestation):
    manifest, backup = with_retired_contest(adapter)
    proof = evidence(manifest)
    proof.pop(attestation)
    with pytest.raises(CleanupError, match="incomplete_contest_retirement_evidence"):
        execute(adapter, manifest, backup, proof=proof)
    assert all(adapter.get_item({"pk": row["pk"], "sk": row["sk"]}) for row in contest_rows())
    assert not adapter.vectors.deleted


def retirement_rule():
    return {
        "name": "old-contest-recovery",
        "arn": f"arn:aws:events:{REGION}:{ACCOUNT}:rule/old-contest-recovery",
        "expected_state": "ABSENT",
    }


@pytest.mark.parametrize("error", ["ResourceNotFoundException", "AccessDeniedException", "InternalException"])
def test_retired_rule_absence_requires_real_not_found_not_permission_or_transient_failure(adapter, error):
    manifest, _ = with_retired_contest(adapter)
    proof = evidence(manifest)
    proof["retired_contest_recovery_rules"] = [retirement_rule()]
    adapter.events.describe_rule.side_effect = ClientError({"Error": {"Code": error}}, "DescribeRule")
    if error == "ResourceNotFoundException":
        adapter.verify_gate(adapter.scope, manifest, proof)
    else:
        with pytest.raises(ClientError):
            adapter.verify_gate(adapter.scope, manifest, proof)
    assert not adapter.vectors.deleted


def test_contest_recovery_inventory_cannot_omit_or_misidentify_or_accept_live_rule(adapter):
    manifest, _ = with_retired_contest(adapter)
    proof = evidence(manifest)
    proof.pop("retired_contest_recovery_rules")
    with pytest.raises(CleanupError, match="contest_recovery_inventory_required"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    proof["retired_contest_recovery_rules"] = [{**retirement_rule(), "arn": retirement_rule()["arn"] + "-wrong"}]
    with pytest.raises(CleanupError, match="rule_identity"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    rule = retirement_rule()
    proof["retired_contest_recovery_rules"] = [rule]
    adapter.events.describe_rule.return_value = {"Arn": rule["arn"], "State": "DISABLED"}
    with pytest.raises(CleanupError, match="contest_recovery_not_retired"):
        adapter.verify_gate(adapter.scope, manifest, proof)
    rule["expected_state"] = "DISABLED"
    adapter.verify_gate(adapter.scope, manifest, proof)
    adapter.events.describe_rule.return_value["State"] = "ENABLED"
    with pytest.raises(CleanupError, match="contest_recovery_not_retired"):
        adapter.verify_gate(adapter.scope, manifest, proof)


def test_retirement_crash_after_meta_delete_resumes_same_backup_and_rejects_changed_outbox(adapter):
    manifest, backup = with_retired_contest(adapter)
    original = adapter.delete_item

    def fail_after_delete(row):
        original(row)
        if row.get("kind") == "contest":
            raise OSError("synthetic post-delete failure")

    adapter.delete_item = fail_after_delete
    with pytest.raises(OSError):
        execute(adapter, manifest, backup)
    outbox = contest_rows()[-1]
    assert adapter.get_item({"pk": outbox["pk"], "sk": outbox["sk"]})
    adapter.delete_item = original
    adapter.table.put_item(Item={**outbox, "created_at": NOW})
    with pytest.raises(CleanupError, match="manifest_content_changed"):
        execute(adapter, manifest, backup)
    adapter.table.put_item(Item=outbox)
    assert execute(adapter, manifest, backup)["online_clean"]


def test_expanding_retirement_scope_invalidates_backup_and_manifest_digest(adapter):
    manifest, backup = with_retired_contest(adapter)
    modified = copy.deepcopy(manifest)
    modified["scope"]["retired_contests"] += ({"chat_id": "-100", "root_message_id": "11"},)
    with pytest.raises(CleanupError, match="backup_manifest_mismatch"):
        validate_backup(modified, backup)
    assert digest(modified) != digest(manifest)
