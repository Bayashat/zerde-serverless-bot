"""Offline replay through the real persistence, worker, lifecycle and answer owners.

Only the AWS transport, provider responses, membership and clock are synthetic.
This module accepts the label-free replay_input contract, never a gold scenario.
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
import logging
import socket
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import boto3
from boto3.dynamodb.types import TypeDeserializer
from moto import mock_aws
from services.memory_budget import MemoryBudgetRepository
from services.memory_v2._cost_catalog import parse_inventory
from services.memory_v2._cost_state import CostState
from services.memory_v2.extraction_prompt import input_upper_bytes
from services.memory_v2.extractor import MemoryExtractor
from services.memory_v2.ingestion import MemoryIngestion, task_payload
from services.memory_v2.lifecycle import MemoryLifecycle
from services.memory_v2.models import (
    AdminConfirmation,
    EvidenceSpan,
    FactChange,
    MemoryInputError,
    MemorySourceConflict,
    MemoryUnavailable,
    SourceEvent,
)
from services.memory_v2.recovery import MemoryRecovery
from services.memory_v2.repository import MemoryRepository
from services.memory_v2.safety import require_public_content
from services.memory_v2.worker import MemoryWorker
from services.memory_v2.writer import FactWriter

from .contract import EvaluationInputError, fingerprint
from .fixture_provider import FixtureProvider, MissingFixture
from .replay_input import EVENT_TYPES, business_rows, validate_projected


def _jsonable(value):
    if isinstance(value, Decimal):
        return int(value) if value == int(value) else float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


class _Queue:
    def __init__(self):
        self.records = []
        self.count = 0

    def send(self, chat_id, ref):
        self.count += 1
        self.records.append({"messageId": f"local-{self.count}", "body": json.dumps(task_payload(chat_id, ref))})


def _table(db, name, *, index=False):
    kwargs = {
        "TableName": name,
        "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        "AttributeDefinitions": [
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    }
    if index:
        kwargs["AttributeDefinitions"] += [
            {"AttributeName": "work_queue", "AttributeType": "S"},
            {"AttributeName": "due_at", "AttributeType": "N"},
        ]
        kwargs["GlobalSecondaryIndexes"] = [
            {
                "IndexName": "work-due",
                "KeySchema": [
                    {"AttributeName": "work_queue", "KeyType": "HASH"},
                    {"AttributeName": "due_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }
        ]
    return db.create_table(**kwargs)


class DomainReplayAdapter:
    provider_kind = "fake_provider"
    requires_projected_input = True

    def __init__(self, catalog):
        self.catalog = catalog
        self.runs = []

    def observe_scenario(self, scenario):
        validate_projected(scenario)
        self.network_attempts = 0

        def forbid_network(*args, **kwargs):
            self.network_attempts += 1
            raise RuntimeError("Offline replay forbids network")

        with ExitStack() as stack:
            stack.enter_context(mock_aws())
            stack.enter_context(
                patch.dict("os.environ", {"AWS_EC2_METADATA_DISABLED": "true", "AWS_DEFAULT_REGION": "eu-central-1"})
            )
            for owner, method in (
                (socket.socket, "connect"),
                (socket.socket, "connect_ex"),
                (socket, "create_connection"),
                (socket, "getaddrinfo"),
            ):
                stack.enter_context(patch.object(owner, method, side_effect=forbid_network))
            db = boto3.resource(
                "dynamodb", region_name="eu-central-1", aws_access_key_id="testing", aws_secret_access_key="testing"
            )
            stack.enter_context(patch("services.memory_v2.repository.get_dynamodb", return_value=db))
            stack.enter_context(patch("services.memory_budget.get_dynamodb", return_value=db))
            self._setup(db, scenario)
            captured = io.StringIO()
            stack.enter_context(redirect_stdout(captured))
            stack.enter_context(redirect_stderr(captured))
            # Observe actual formatter output, including non-propagating JSON
            # handlers. Synthetic SDK debug transport is not application output.
            handle = logging.Handler.handle

            def observe_log(handler, record):
                if not record.name.startswith(("botocore", "boto3", "moto", "urllib3")):
                    self.logs.append(handler.format(record))
                return handle(handler, record)

            stack.enter_context(patch.object(logging.Handler, "handle", observe_log))
            observations = asyncio.run(self._run(scenario))
            if self.network_attempts:
                raise EvaluationInputError("Replay attempted forbidden network access")
            if captured.getvalue():
                self.logs.append(captured.getvalue())
            # Capture output emitted at the final checkpoint as well.
            for observation in observations:
                observation["traces"]["safety_surfaces"]["logs"] = list(self.logs)
            self.runs.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "events": copy.deepcopy(self.event_trace),
                    "missing_fixtures": copy.deepcopy(self.missing),
                    "network_calls": 0,
                }
            )
            return observations

    def _setup(self, db, scenario):
        self.clock = SimpleNamespace(now=scenario["learning_started_at"])
        table = _table(db, "local-memory-replay", index=True)
        self.business = _table(db, "local-legacy-business")
        self.business_stats = db.create_table(
            TableName="local-preserved-stats",
            KeySchema=[{"AttributeName": "stat_key", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "stat_key", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        self.repo = MemoryRepository(table.name, clock=lambda: self.clock.now)
        self.raw_capture = []
        self._capture_raw_writes()
        self.writer, self.lifecycle = FactWriter(self.repo), MemoryLifecycle(self.repo)
        self.queue = _Queue()
        receipts = SimpleNamespace(list_clean_pending=lambda **_: ([], None))
        self.ingestion = MemoryIngestion(self.repo, receipts, self.queue)
        self.recovery = MemoryRecovery(self.ingestion)
        inventory = parse_inventory(
            json.dumps(
                {
                    "schema": 1,
                    "region": "eu-central-1",
                    "account_id": "000000000000",
                    "metering_started_at": self.clock.now,
                    "alarm_count": 10,
                }
            )
        )
        self.budget = MemoryBudgetRepository(
            table.name, clock=lambda: self.clock.now, inventory_version=inventory.version
        )
        self.cost_state = CostState(self.budget, clock=lambda: self.clock.now)
        self.requests, self.sent, self.logs, self.missing, self.event_trace = [], [], [], [], []
        self.sources, self.refs, self.work_archive = {}, {}, {}
        self.chats = tuple(dict.fromkeys(e["chat_id"] for e in scenario["events"]))
        for chat in self.chats:
            self.repo.activate_group(chat, expected_revision=0)
        self.business_seed = business_rows(self.chats[0], scenario["business_seed"])
        for row in self.business_seed.values():
            table, _ = self._business_storage(row)
            table.put_item(Item=row)
        self.before = self._business_snapshot()
        self.extract_provider = FixtureProvider(self.catalog, kind="extraction", trace=self.requests)
        self.answer_provider = FixtureProvider(self.catalog, kind="answer", trace=self.requests)
        self.quota = SimpleNamespace(increment_and_check=lambda: (1, True))
        self.worker = MemoryWorker(
            self.repo,
            lambda validate: MemoryExtractor(
                provider=self.extract_provider,
                budget=self.budget,
                validate_sources=validate,
                rate_limit=self.quota,
                clock=lambda: self.clock.now,
            ),
            sizing_fn=input_upper_bytes,
        )

    def _capture_raw_writes(self):
        """Observe persisted RAW at each successful native SDK write boundary.

        Moto is synchronous: the strong read runs before the next replay write,
        so a later purge cannot erase evidence of a transient unsafe admission.
        These synthetic traces are never passed to the provider or writer.
        """
        deserialize = TypeDeserializer().deserialize
        context_key = "memory_eval_raw_write_keys"

        def before_call(model, params, context, **_):
            body = json.loads(params["body"])
            operation = model.name
            if operation in {"PutItem", "UpdateItem"}:
                writes = [body]
            elif operation == "TransactWriteItems":
                writes = [item[kind] for item in body["TransactItems"] for kind in ("Put", "Update") if kind in item]
            else:
                writes = [
                    {"TableName": name, **item["PutRequest"]}
                    for name, items in body["RequestItems"].items()
                    for item in items
                    if "PutRequest" in item
                ]
            keys = []
            for item in writes:
                if item["TableName"] != self.repo.table.name:
                    continue
                wire = item.get("Item", item.get("Key"))
                key = {name: deserialize(wire[name]) for name in ("pk", "sk")}
                if key["sk"].startswith("RAW#"):
                    keys.append(key)
            context[context_key] = keys

        def after_call(http_response, context, **_):
            if http_response.status_code >= 300:
                return
            if context_key not in context:
                raise EvaluationInputError("RAW write capture has no matching request trace")
            for key in context[context_key]:
                row = self.repo.table.get_item(Key=key, ConsistentRead=True).get("Item")
                # A batch may contain an unprocessed put. Existing persisted RAW
                # is still an actual surface; a missing item contributes no text.
                if row is not None and "text" in row:
                    if not isinstance(row["text"], str):
                        raise EvaluationInputError("RAW capture contains an unsupported text shape")
                    self.raw_capture.append(row["text"])

        for operation in ("PutItem", "UpdateItem", "TransactWriteItems", "BatchWriteItem"):
            self.repo.table.meta.client.meta.events.register_first(f"before-call.dynamodb.{operation}", before_call)
            self.repo.table.meta.client.meta.events.register(f"after-call.dynamodb.{operation}", after_call)

    def _business_snapshot(self):
        snapshots = {}
        for name, row in self.business_seed.items():
            table, key = self._business_storage(row)
            snapshots[name] = fingerprint(_jsonable(table.get_item(Key=key, ConsistentRead=True).get("Item")))
        return snapshots

    def _business_storage(self, row):
        if "stat_key" in row:
            return self.business_stats, {"stat_key": row["stat_key"]}
        return self.business, {"pk": row["pk"], "sk": row["sk"]}

    async def _run(self, scenario):
        observations = []
        for event in scenario["events"]:
            await self._event(event)
            for checkpoint in scenario["checkpoints"]:
                if checkpoint["after_event"] == event["event_id"]:
                    await self._drain()
                    observations.append(await self._checkpoint(scenario, checkpoint))
        return observations

    def _source(self, event):
        kind = "confirmation" if event["type"] == "admin_confirmation" else "message"
        if event["type"] == "edit":
            original = self.repo.get_observation(event["chat_id"], event["message_id"])
            if original:
                kind = original["source_kind"]
        return SourceEvent(
            event["chat_id"],
            event["message_id"],
            event["user_id"],
            event["original_sent_at"],
            event["text"],
            edited_at=event["edited_at"],
            is_bot=event.get("is_bot", False),
            is_forwarded=event.get("forwarded", False),
            quoted_spans=tuple(tuple(span) for span in event.get("quoted_spans", [])),
            source_kind=kind,
        )

    async def _event(self, event):
        kind, chat = event["type"], event["chat_id"]
        if kind not in EVENT_TYPES:
            raise EvaluationInputError("Unsupported replay event")
        self.clock.now = max(self.clock.now + 1, event.get("original_sent_at", 0), event.get("edited_at", 0))
        status = "APPLIED"
        try:
            if kind in {"message", "edit", "admin_confirmation"}:
                source = self._source(event)
                self.sources[event["event_id"]] = copy.deepcopy(event)
                ref = self.ingestion.observe(source)
                self.refs[event["event_id"]] = (chat, ref)
                # Editing a command invalidates its earlier confirmation, but
                # does not create a new command authorization or extraction job.
                if kind == "edit" and source.source_kind == "confirmation":
                    self.event_trace.append({"event_id": event["event_id"], "kind": kind, "status": "INVALIDATED"})
                    return
                require_public_content(source.text, max_length=20000)
                ref = self.ingestion.accept_safe(source)
                if kind == "admin_confirmation":
                    declaration = self.catalog.get("confirmation", source.text)
                    if (
                        set(declaration) != {"authorized_actor_ids", "changes"}
                        or source.actor_user_id not in declaration["authorized_actor_ids"]
                    ):
                        raise EvaluationInputError("Confirmation needs independent live-admin fixture identity")
                    group = self.repo.ensure_subject(chat, "GROUP")
                    self.writer.confirm_group_fact(
                        chat,
                        ref,
                        expected_subject_revision=int(group["revision"]),
                        changes=[
                            FactChange(
                                row["field"],
                                row["value"],
                                EvidenceSpan(row["start"], row["end"]),
                                assertion_kind="admin_confirmed",
                            )
                            for row in declaration["changes"]
                        ],
                        confirmation=AdminConfirmation(source.actor_user_id, True),
                    )
            elif kind in {"forget_user", "forget_source", "forget_group", "optout", "new_epoch"}:
                scope = (
                    "group"
                    if kind in {"forget_group", "new_epoch"}
                    else "source" if kind == "forget_source" else "subject"
                )
                target = event.get("message_id") if scope == "source" else event.get("user_id")
                self._archive_work()
                job = self.lifecycle.begin(chat, scope=scope, target=target, optout=kind == "optout")
                for _ in range(10):
                    job = self.lifecycle.advance(chat, job["sk"], max_pages=4)
                    if job["state"] == "DONE":
                        break
                else:
                    raise EvaluationInputError("Deletion did not complete within replay bound")
                for key, trace in self.work_archive.items():
                    if key.startswith(chat + ":") and trace["state"] in {"PENDING", "LEASED", "PAUSED"}:
                        work = self.repo._read(chat, key[len(chat) + 1 :])
                        if not work:
                            trace.update(state="EXPIRED", reason="purged", terminal_source="completed_purge")
                if kind == "new_epoch":
                    self.repo.activate_group(chat, expected_revision=int(self.repo.get_control(chat)["revision"]))
            elif kind == "optin":
                subject = self.repo.get_subject(chat, event["user_id"])
                self.repo.opt_in(chat, event["user_id"], expected_revision=int(subject["revision"]))
            elif kind == "learning_pause":
                self.repo.set_learning_enabled(
                    chat, False, expected_revision=int(self.repo.get_control(chat)["revision"])
                )
            elif kind in {"provider_failure", "provider_resume"}:
                self.extract_provider.failed = kind == "provider_failure"
                if kind == "provider_resume":
                    self.clock.now += 61
                    self.recovery.run()
            elif kind == "budget_pause":
                # Explicit injected external control state, not a second production writer.
                self.budget.table.put_item(Item={"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL", "paused": True})
            elif kind in {"advance_time", "pending_expiry"}:
                self.clock.now += event["seconds"]
                self.recovery.run()
            elif kind == "task_replay":
                if event["source_event"] not in self.refs:
                    raise EvaluationInputError("Replay references an unobserved source")
                old_chat, old_ref = self.refs[event["source_event"]]
                self.queue.send(old_chat, old_ref)
        except MissingFixture:
            self.missing.append({"event_id": event["event_id"], "kind": kind})
            status = "UNSUPPORTED_FIXTURE"
        except (MemoryInputError, MemorySourceConflict, MemoryUnavailable) as exc:
            if kind not in {"message", "edit"}:
                raise EvaluationInputError(f"Replay control {kind} failed: {type(exc).__name__}") from exc
            status = type(exc).__name__
        self.event_trace.append({"event_id": event["event_id"], "kind": kind, "status": status})

    async def _drain(self):
        # This is an explicitly synthetic telemetry fixture, using the real
        # CAS owner and inventory hash gate. It never unpauses MODEL controls.
        self.cost_state.record_measurement(
            self.budget.month(),
            inventory_version=self.budget.inventory_version,
            verified=True,
            estimate=0,
            covered_until=self.clock.now,
            reason="SYNTHETIC_OFFLINE_FIXTURE_NOT_AWS_MEASUREMENT",
        )
        records, self.queue.records = self.queue.records, []
        if records:
            result = await self.worker.handle_records(records)
            if result["batchItemFailures"]:
                raise EvaluationInputError("Domain worker failed during replay")
        self._archive_work()
        self.missing += self.extract_provider.missing
        self.extract_provider.missing = []

    def _archive_work(self):
        for chat in self.chats:
            for row in self.repo._list(chat, "WORK#"):
                key = chat + ":" + row["sk"]
                state = row["state"]
                if state == "PENDING" and row.get("last_reason") in {"paused", "learning_paused", "budget"}:
                    state = "PAUSED"
                self.work_archive[key] = {
                    "work_id": key,
                    "state": state,
                    "reason": row.get("last_reason", ""),
                    "source_ref": _jsonable(row["source_ref"]),
                    "age_seconds": max(0, self.clock.now - int(row["created_at"])),
                    "lane": "recovery" if "first_recovery_at" in row else "normal",
                    **(
                        {"elapsed_seconds": max(0, int(row["completed_at"]) - int(row["original_sent_at"]))}
                        if "completed_at" in row
                        else {}
                    ),
                }

    def _fact(self, chat, fact):
        ref = fact["evidence"]["source_ref"]
        matches = [key for key, (scope, known) in self.refs.items() if scope == chat and known.as_dict() == ref]
        if not matches:
            raise EvaluationInputError("Persisted fact evidence has no replay source")
        event = self.sources[matches[-1]]
        excerpt = fact["evidence"]["excerpt"]
        positions = []
        start = event["text"].find(excerpt)
        while start >= 0:
            if not any(start < right and start + len(excerpt) > left for left, right in event.get("quoted_spans", [])):
                positions.append(start)
            start = event["text"].find(excerpt, start + 1)
        if len(positions) != 1:
            raise EvaluationInputError("Persisted evidence is absent or ambiguous in original input")
        start = positions[0]
        return {
            "fact_id": fact["fact_id"],
            "chat_id": chat,
            "subject_id": "group" if fact["subject_id"] == "GROUP" else fact["subject_id"].removeprefix("USER#"),
            "field": fact["field"],
            "facet": fact["facet"],
            "value": fact["value"],
            "temporal_status": fact["freshness"],
            "evidence": {"source_event": matches[-1], "start": start, "end": start + len(excerpt)},
        }

    async def _checkpoint(self, scenario, checkpoint):
        facts = []
        for chat in self.chats:
            for subject in self.repo._list(chat, "SUBJECT#"):
                identity = "GROUP" if subject["sk"] == "SUBJECT#GROUP" else subject["sk"].removeprefix("SUBJECT#USER#")
                try:
                    facts += [self._fact(chat, fact) for fact in self.repo.get_profile(chat, identity)]
                except MemoryUnavailable:
                    pass
        answers = []
        for question in checkpoint["questions"]:
            answer = await self._answer(question, scenario["language"])
            if answer is not None:
                answers.append(answer)
        self.missing += self.answer_provider.missing
        self.answer_provider.missing = []
        return {
            "scenario_id": scenario["scenario_id"],
            "checkpoint_id": checkpoint["checkpoint_id"],
            "facts": facts,
            "answers": answers,
            "replay": {
                "state": "UNSUPPORTED" if self.missing else "EXECUTED",
                "events": copy.deepcopy(self.event_trace),
                "missing_fixtures": copy.deepcopy(self.missing),
                "network_calls": 0,
            },
            "traces": {
                "business_trace_schema": 2,
                "business_before": self.before,
                "business_after": self._business_snapshot(),
                "sent_actions": copy.deepcopy(self.sent),
                "safety_surfaces": {
                    "raw": list(self.raw_capture),
                    "context": [json.dumps(row, ensure_ascii=False) for row in self.requests],
                    "logs": list(self.logs),
                    "answers": [row["text"] for row in self.sent],
                },
                "work": copy.deepcopy(list(self.work_archive.values())),
                "budget_ledger": {
                    "evidence_kind": "actual_moto_transactions_synthetic_usage_and_aws_measurement",
                    "model": _jsonable(self.budget.snapshot()),
                    "aws": _jsonable(self.cost_state.read(self.budget.month(), "AWS")),
                },
            },
        }

    async def _answer(self, question, language):
        # These imports intentionally fail when the reviewed Z08 answer owner is
        # absent; there is no hand-written stand-in for the production path.
        from services.memory_v2.answer_rendering import unknown_text
        from services.memory_v2.answer_selector import AnswerSelectionUnavailable, MemoryAnswerSelector
        from services.memory_v2.answers import MemoryAnswerService

        sent = []

        async def sender(chat, text, *, reply_to_message_id):
            identifier = 1_000_000 + len(self.sent)
            sent.append(identifier)
            self.sent.append({"kind": "explicit_answer", "chat_id": str(chat), "message_id": identifier, "text": text})
            return identifier

        service = MemoryAnswerService(
            self.repo,
            authorize=lambda *_: True,
            sender=sender,
            selector_factory=lambda validate: MemoryAnswerSelector(
                self.answer_provider, self.budget, validate_snapshot=validate, rate_limit=self.quota
            ),
        )
        target = question.get("target_subject_id", question["requester_id"])
        target = "GROUP" if target == "group" else target
        try:
            outcome = await service.answer(
                question["chat_id"],
                question["requester_id"],
                [target],
                request_id=question["question_id"],
                question=question["text"],
                lang=language,
                reply_to_message_id=900_000 + len(self.sent),
            )
        except (MemoryUnavailable, MemoryInputError, AnswerSelectionUnavailable):
            return None
        if outcome.state != "SENT":
            return None
        assertions = []
        for identifier in sent:
            receipt = self.repo._read(question["chat_id"], "ANSWER_REPLY#" + str(identifier))
            for ref in receipt["fact_refs"]:
                fact = self.repo._read(question["chat_id"], ref["fact_id"])
                current = self.repo.get_profile(question["chat_id"], target)
                matching = next((row for row in current if row["fact_id"] == fact["fact_id"]), None)
                if matching:
                    converted = self._fact(question["chat_id"], matching)
                    if converted not in assertions:
                        assertions.append(converted)
        texts = [row["text"] for row in self.sent if row["message_id"] in sent]
        return {
            "question_id": question["question_id"],
            "assertions": assertions,
            "abstained": not assertions and texts == [unknown_text(language)],
        }
