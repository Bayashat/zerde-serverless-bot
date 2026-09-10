"""Narrow AWS API surface: read inventory, exact-key deletes, no resource/queue purge."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import boto3
from botocore.config import Config

from .policy import CleanupError, digest, item_key

HASH = re.compile(r"[a-f0-9]{64}\Z")
ATTESTATIONS = (
    "all_legacy_readers_stopped",
    "all_legacy_item_writers_stopped",
    "explicit_threads_stopped_or_migrated",
    "media_groups_stopped_or_migrated",
    "external_import_writers_stopped",
    "history_apply_blocked",
    "old_task_replay_verified",
    "complete_writer_consumer_inventory",
    "complete_legacy_index_inventory",
    "selected_indexes_contain_only_retired_memory",
    "change_freeze_active",
)


def condition_for(row):
    """DDB cannot condition on a computed whole-item hash or unknown added fields."""
    names = {}
    values = {}
    parts = []
    for index, (name, value) in enumerate(sorted(row.items())):
        names[f"#a{index}"] = name
        values[f":v{index}"] = value
        parts.append(f"#a{index} = :v{index}")
    expression = " AND ".join(parts)
    if len(expression.encode()) > 4000:
        raise CleanupError("item_condition_too_wide_for_safe_delete")
    return {"ConditionExpression": expression, "ExpressionAttributeNames": names, "ExpressionAttributeValues": values}


def _timestamp(value):
    if isinstance(value, datetime):
        return value.timestamp()
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def normalize_vector(row):
    return {"key": row["key"], "data": row["data"], "metadata": row.get("metadata", {})}


class AWSAdapter:
    def __init__(self, scope, *, session=None, clock=time.time):
        self.scope = scope
        self.clock = clock
        session = session or boto3.Session(region_name=scope.region)
        config = Config(connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 1})
        self.sts = session.client("sts", region_name=scope.region, config=config)
        self.ddb = session.resource("dynamodb", region_name=scope.region, config=config)
        self.table = self.ddb.Table(scope.table_arn.rsplit("/", 1)[1])
        self.vectors = session.client("s3vectors", region_name=scope.region, config=config)
        self.functions = session.client("lambda", region_name=scope.region, config=config)
        self.events = session.client("events", region_name=scope.region, config=config)
        self.queues = session.client("sqs", region_name=scope.region, config=config)

    def identity(self, scope):
        if scope != self.scope or self.sts.get_caller_identity()["Account"] != scope.account_id:
            raise CleanupError("account_or_scope_mismatch")
        table = self.ddb.meta.client.describe_table(TableName=self.table.name)["Table"]
        if table["TableArn"] != scope.table_arn or table["TableStatus"] != "ACTIVE":
            raise CleanupError("table_identity_or_status_mismatch")
        schema = sorted(table["KeySchema"], key=lambda value: value["KeyType"])
        expected = [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}]
        types = {value["AttributeName"]: value["AttributeType"] for value in table["AttributeDefinitions"]}
        if schema != expected or types.get("pk") != "S" or types.get("sk") != "S":
            raise CleanupError("unexpected_legacy_table_schema")
        indexes = {}
        for arn in scope.index_arns:
            index = self.vectors.get_index(indexArn=arn)["index"]
            if index["indexArn"] != arn:
                raise CleanupError("index_identity_mismatch")
            indexes[arn] = index
        return {
            "account_id": scope.account_id,
            "region": scope.region,
            "table": {key: table.get(key) for key in ("TableArn", "TableId", "CreationDateTime", "KeySchema")},
            "indexes": indexes,
        }

    def scan_rows(self):
        rows, seen = [], set()
        args = {"ConsistentRead": True, "Limit": 200}
        while True:
            page = self.table.scan(**args)
            rows.extend(page.get("Items", []))
            cursor = page.get("LastEvaluatedKey")
            if not cursor:
                return rows
            marker = digest(cursor)
            if marker in seen:
                raise CleanupError("table_pagination_cycle")
            seen.add(marker)
            args["ExclusiveStartKey"] = cursor

    def list_vectors(self, arn):
        if arn not in self.scope.index_arns:
            raise CleanupError("index_outside_scope")
        rows, seen = [], set()
        args = {"indexArn": arn, "maxResults": 500, "returnData": True, "returnMetadata": True}
        while True:
            page = self.vectors.list_vectors(**args)
            rows.extend(normalize_vector(row) for row in page.get("vectors", []))
            cursor = page.get("nextToken")
            if not cursor:
                return rows
            if cursor in seen:
                raise CleanupError("vector_pagination_cycle")
            seen.add(cursor)
            args["nextToken"] = cursor

    def snapshot(self, scope):
        identity = self.identity(scope)
        result = {
            "identity": identity,
            "rows": self.scan_rows(),
            "vectors": {arn: self.list_vectors(arn) for arn in scope.index_arns},
        }
        if identity != self.identity(scope):
            raise CleanupError("resource_recreated_during_inventory")
        return result

    def get_vectors(self, arn, keys):
        if arn not in self.scope.index_arns:
            raise CleanupError("index_outside_scope")
        rows = self.vectors.get_vectors(indexArn=arn, keys=keys, returnData=True, returnMetadata=True)["vectors"]
        if len({row["key"] for row in rows}) != len(rows) or any(row["key"] not in keys for row in rows):
            raise CleanupError("unexpected_get_vectors_response")
        return {row["key"]: normalize_vector(row) for row in rows}

    def delete_vectors(self, arn, keys):
        if arn not in self.scope.index_arns or not 1 <= len(keys) <= 25:
            raise CleanupError("invalid_vector_delete_scope")
        self.vectors.delete_vectors(indexArn=arn, keys=keys)

    def get_item(self, key):
        return self.table.get_item(Key=key, ConsistentRead=True).get("Item")

    def validate_delete_condition(self, row):
        condition_for(row)

    def delete_item(self, row):
        self.table.delete_item(Key=item_key(row), **condition_for(row))

    def _inventory(self, method, result_key, **kwargs):
        items, seen = [], set()
        while True:
            result = method(**kwargs)
            items.extend(result.get(result_key, []))
            marker = result.get("NextMarker")
            if not marker:
                return items
            if marker in seen:
                raise CleanupError("gate_inventory_pagination_cycle")
            seen.add(marker)
            kwargs["Marker"] = marker

    def verify_gate(self, scope, manifest, evidence):
        """Live readback plus explicitly reviewed stop evidence, never a guard flag alone.

        AWS cannot prove source semantics or external clients are stopped. The reviewed
        evidence digest attests these facts; all executable targets/aliases/consumers
        must be enumerated and their live revision compared on every mutation batch.
        """
        now = int(self.clock())
        if (
            evidence.get("format") != "zerde-legacy-cutover-evidence-v1"
            or evidence.get("manifest_sha256") != digest(manifest)
            or not HASH.fullmatch(evidence.get("reviewed_evidence_sha256", ""))
            or any(evidence.get(name) is not True for name in ATTESTATIONS)
        ):
            raise CleanupError("incomplete_reviewed_stop_evidence")
        observed, expires, stopped = (evidence.get(key) for key in ("observed_at", "valid_until", "stopped_at"))
        if (
            any(type(value) is not int for value in (observed, expires, stopped))
            or not stopped <= observed <= now < expires <= observed + 900
        ):
            raise CleanupError("cutover_evidence_not_fresh")
        if manifest["created_at"] < stopped:
            raise CleanupError("manifest_predates_complete_writer_stop")
        targets = evidence.get("lambda_targets")
        if not isinstance(targets, list) or not targets:
            raise CleanupError("incomplete_lambda_guard_inventory")
        target_arns = {target.get("function_arn", "") for target in targets}
        base_roles = {target.get("role") for target in targets if target.get("function_arn", "").count(":") == 6}
        if not {"bot", "vector_indexer"}.issubset(base_roles):
            raise CleanupError("incomplete_lambda_guard_inventory")
        maximum = evidence.get("old_max_timeout_seconds")
        if type(maximum) is not int or not 900 <= maximum <= 43200 or now < stopped + maximum + 60:
            raise CleanupError("old_invocations_not_drained")
        if self.identity(scope) != manifest["identity"]:
            raise CleanupError("gate_resource_identity_changed")
        arns = set()
        for target in targets:
            arn = target.get("function_arn", "")
            arn_prefix = f"arn:aws:lambda:{scope.region}:{scope.account_id}:function:"
            if not arn.startswith(arn_prefix) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,64}(:[1-9][0-9]*)?", arn[len(arn_prefix) :]
            ):
                raise CleanupError("lambda_outside_account_or_region")
            base_arn = ":".join(arn.split(":")[:7])
            if base_arn not in target_arns:
                raise CleanupError("unverified_unqualified_function")
            if arn in arns:
                raise CleanupError("duplicate_lambda_target")
            arns.add(arn)
            live = self.functions.get_function_configuration(FunctionName=arn)
            if (
                live["FunctionArn"] != arn
                or live["RevisionId"] != target.get("revision_id")
                or live["CodeSha256"] != target.get("code_sha256")
                or live.get("State") != "Active"
                or (arn == base_arn and live.get("LastUpdateStatus") != "Successful")
                or maximum < live["Timeout"]
                or _timestamp(live["LastModified"]) > stopped
            ):
                raise CleanupError("lambda_guard_artifact_or_revision_changed")
            if arn != base_arn:
                # Immutable published versions have no separate aliases/consumer inventory.
                continue
            aliases = self._inventory(self.functions.list_aliases, "Aliases", FunctionName=base_arn)
            aliases = sorted(
                (
                    {key: row.get(key) for key in ("AliasArn", "FunctionVersion", "RevisionId", "RoutingConfig")}
                    for row in aliases
                ),
                key=lambda row: row["AliasArn"],
            )
            if any((row.get("RoutingConfig") or {}).get("AdditionalVersionWeights") for row in aliases):
                raise CleanupError("weighted_alias_not_drained")
            if aliases != target.get("aliases"):
                raise CleanupError("lambda_alias_inventory_changed")
            # An alias must point at another explicitly verified version target.
            for alias in aliases:
                version_arn = (
                    arn.split(":function:", 1)[0]
                    + ":function:"
                    + arn.split(":function:", 1)[1].split(":")[0]
                    + ":"
                    + alias["FunctionVersion"]
                )
                if version_arn not in target_arns:
                    raise CleanupError("unverified_alias_version")
            mappings = self._inventory(
                self.functions.list_event_source_mappings, "EventSourceMappings", FunctionName=arn
            )
            mappings = sorted(
                ({key: row.get(key) for key in ("UUID", "EventSourceArn", "FunctionArn", "State")} for row in mappings),
                key=lambda row: row["UUID"],
            )
            verified_routes = target_arns | {alias["AliasArn"] for alias in aliases}
            if any(row["FunctionArn"] not in verified_routes for row in mappings):
                raise CleanupError("unverified_consumer_function_version")
            if any(row["State"] not in ("Enabled", "Disabled") for row in mappings) or mappings != target.get(
                "event_sources"
            ):
                raise CleanupError("consumer_inventory_changed_or_transitioning")
        rules = evidence.get("disabled_legacy_rules")
        if not isinstance(rules, list):
            raise CleanupError("schedule_inventory_required")
        for rule in rules:
            live = self.events.describe_rule(Name=rule["name"], EventBusName=rule.get("event_bus", "default"))
            if (
                live["Arn"] != rule["arn"]
                or live["State"] != "DISABLED"
                or not live["Arn"].startswith(f"arn:aws:events:{scope.region}:{scope.account_id}:rule/")
            ):
                raise CleanupError("legacy_schedule_not_disabled")
        queues = evidence.get("queues")
        if not isinstance(queues, list) or not queues:
            raise CleanupError("queue_retention_inventory_required")
        for queue in queues:
            attrs = self.queues.get_queue_attributes(
                QueueUrl=queue["url"],
                AttributeNames=[
                    "QueueArn",
                    "MessageRetentionPeriod",
                    "VisibilityTimeout",
                    "ApproximateNumberOfMessagesNotVisible",
                ],
            )["Attributes"]
            if (
                attrs["QueueArn"] != queue["arn"]
                or not attrs["QueueArn"].startswith(f"arn:aws:sqs:{scope.region}:{scope.account_id}:")
                or attrs["MessageRetentionPeriod"] != str(queue["retention_seconds"])
                or attrs["VisibilityTimeout"] != str(queue["visibility_timeout_seconds"])
            ):
                raise CleanupError("queue_identity_or_retention_changed")
            # Mixed business queues may have live messages. No body read/delete/purge.
            if queue.get("dedicated_legacy") is True and attrs["ApproximateNumberOfMessagesNotVisible"] != "0":
                raise CleanupError("dedicated_legacy_queue_not_drained")
        if int(self.clock()) >= expires:
            raise CleanupError("cutover_evidence_expired_during_readback")
