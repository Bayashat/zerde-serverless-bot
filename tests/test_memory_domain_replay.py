"""Real owner replay with synthetic provider fixtures; never model acceptance."""

import copy
import json
import socket
from pathlib import Path

import pytest

from dev.tools.memory_eval.contract import EvaluationInputError, read_jsonl
from dev.tools.memory_eval.domain_adapter import DomainReplayAdapter
from dev.tools.memory_eval.fixture_authoring import author_fixture_rows
from dev.tools.memory_eval.fixture_provider import FixtureCatalog, text_hash
from dev.tools.memory_eval.replay_input import EVENT_TYPES, project_scenario
from dev.tools.memory_eval.runner import collect_observations

CORPUS = Path(__file__).parent / "fixtures/memory_v2_eval/scenarios.jsonl"


def scenario(number=1, lang="en"):
    return copy.deepcopy(next(row for row in read_jsonl(CORPUS) if row["scenario_id"] == f"{lang}-{number:03d}"))


def row(kind, text, response):
    return {"kind": kind, "input_text": text, "input_sha256": text_hash(text), "response": response}


def fixtures(source):
    # Deliberately narrow hand-authored synthetic provider. Occupation is omitted
    # even though gold expects it, demonstrating the adapter cannot copy labels.
    records = []
    seen = set()
    for event in source["events"]:
        if "text" not in event or event["text"] in seen:
            continue
        text = event["text"]
        seen.add(text)
        facts = []
        if text == "I use Python for my work.":
            facts = [
                {
                    "field": "tech_stack",
                    "value": "Python",
                    "evidence": text,
                    "action": "assert",
                    "facet": "",
                    "attribution": "self_explicit",
                }
            ]
        records.append(row("extraction", text, {"facts": facts}))
    questions = {q["text"] for cp in source["checkpoints"] for q in cp["questions"]}
    records += [row("answer", text, {"fields": ["location"] if "city" in text else ["*"]}) for text in questions]
    return FixtureCatalog(records)


def test_projection_removes_all_gold_and_annotation_channels():
    source = scenario()
    projected = project_scenario(source)
    serialized = json.dumps(projected)
    for label in ("supporting_fact_ids", "accepted_values", "requested_fields", "safe", "tags", "expected", "facts"):
        assert f'"{label}"' not in serialized
    assert set(event["type"] for s in read_jsonl(CORPUS) for event in s["events"]) == EVENT_TYPES


def test_real_worker_profile_answer_and_business_snapshots_do_not_copy_gold():
    source = scenario()
    adapter = DomainReplayAdapter(fixtures(source))
    observed = collect_observations([source], adapter)[0]
    assert observed["replay"]["state"] == "EXECUTED"
    assert [fact["value"] for fact in observed["facts"]] == ["Python"]
    assert observed["facts"][0]["evidence"]["source_event"] == "m3"
    assert all(row["state"] == "DONE" for row in observed["traces"]["work"])
    assert observed["traces"]["business_before"] == observed["traces"]["business_after"]
    assert observed["traces"]["business_before"] != source["protected_business"]
    assert len(observed["answers"]) == 2 and observed["answers"][1]["abstained"]
    assert [item["kind"] for item in observed["traces"]["sent_actions"]] == ["explicit_answer", "explicit_answer"]
    ledger = observed["traces"]["budget_ledger"]
    assert ledger["model"]["charged_micro_usd"] > 0
    assert ledger["aws"]["measurement_state"] == "ESTIMATE_VERIFIED"
    assert ledger["aws"]["reason"] == "SYNTHETIC_OFFLINE_FIXTURE_NOT_AWS_MEASUREMENT"


def test_direct_unprojected_gold_and_unknown_event_are_rejected():
    source = scenario()
    with pytest.raises(EvaluationInputError):
        DomainReplayAdapter(fixtures(source)).observe_scenario(source)
    source["events"].append({"event_id": "oops", "type": "silently_skip"})
    with pytest.raises(EvaluationInputError):
        project_scenario(source)


def test_missing_fixture_is_pending_unsupported_not_successful_empty_extraction():
    source = scenario()
    observed = collect_observations([source], DomainReplayAdapter(FixtureCatalog([])))[0]
    assert observed["replay"]["state"] == "UNSUPPORTED"
    assert observed["facts"] == []
    assert all(item["state"] == "PENDING" for item in observed["traces"]["work"])
    assert observed["answers"] == []  # GENERAL/no actual send cannot become successful abstention.


def with_events(*events):
    source = scenario()
    actor, chat = source["events"][0]["user_id"], source["events"][0]["chat_id"]
    for index, event in enumerate(events, 3):
        source["events"].append({"event_id": f"e{index}", "chat_id": chat, "user_id": actor, **event})
    source["checkpoints"].append(
        {"checkpoint_id": "after", "after_event": source["events"][-1]["event_id"], "questions": [], "facts": []}
    )
    return source


def execute(source):
    catalog = FixtureCatalog(author_fixture_rows([project_scenario(source)]))
    return collect_observations([source], DomainReplayAdapter(catalog))


@pytest.mark.parametrize("kind", ["forget_user", "forget_source", "forget_group", "new_epoch", "optout"])
def test_real_purge_and_old_task_replay_cannot_resurrect_facts(kind):
    source = with_events({"type": kind, "message_id": "12"}, {"type": "task_replay", "source_event": "m3"})
    before, after = execute(source)
    assert before["facts"] and after["facts"] == []
    assert after["traces"]["business_before"] == after["traces"]["business_after"]


@pytest.mark.parametrize("text", ["", "My password is SYNTHETIC-SECRET-ONLY."])
def test_real_paused_unsafe_edit_invalidates_existing_fact_without_persisting_body(text):
    source = with_events(
        {"type": "learning_pause"},
        {
            "type": "edit",
            "message_id": "12",
            "text": text,
            "original_sent_at": 2_000_000_002,
            "edited_at": 2_000_000_005,
        },
    )
    before, after = execute(source)
    assert before["facts"] and after["facts"] == []
    assert text not in after["traces"]["safety_surfaces"]["raw"]


@pytest.mark.parametrize(
    "control,state", [("provider_failure", "PENDING"), ("budget_pause", "PAUSED"), ("pending_expiry", "EXPIRED")]
)
def test_real_worker_faults_keep_explicit_pending_paused_expired_states(control, state):
    source = with_events(
        {
            "type": "message",
            "message_id": "13",
            "text": "I use Rust.",
            "original_sent_at": 2_000_000_004,
            "edited_at": 0,
        },
        {"type": control, "seconds": 31 * 86400},
    )
    before, after = execute(source)
    work = next(item for item in after["traces"]["work"] if item["source_ref"]["source_id"] == "13")
    assert work["state"] == state
    assert all(fact["value"] != "Rust" for fact in after["facts"])
    if control == "budget_pause":
        assert after["traces"]["budget_ledger"]["model"] == before["traces"]["budget_ledger"]["model"]
        assert after["traces"]["safety_surfaces"]["context"] == before["traces"]["safety_surfaces"]["context"]


def test_real_recovery_resumes_due_work_and_commits_once():
    source = with_events(
        {
            "type": "message",
            "message_id": "13",
            "text": "I use Rust.",
            "original_sent_at": 2_000_000_004,
            "edited_at": 0,
        },
        {"type": "provider_failure"},
        {"type": "provider_resume"},
    )
    source["checkpoints"].insert(1, {"checkpoint_id": "pending", "after_event": "e4", "facts": [], "questions": []})
    _, pending, after = execute(source)
    assert any(row["state"] == "PENDING" for row in pending["traces"]["work"])
    assert [fact["value"] for fact in after["facts"]].count("Rust") == 1
    assert all(row["state"] == "DONE" for row in after["traces"]["work"])
    assert any(row["lane"] == "recovery" for row in after["traces"]["work"])


def test_raw_logical_expiry_keeps_real_retained_minimal_fact_evidence():
    source = with_events({"type": "advance_time", "seconds": 31 * 86400})
    before, after = execute(source)
    assert after["facts"] == before["facts"]


def test_poisoned_gold_cannot_change_the_providers_inputs_or_runtime_facts():
    source = scenario()
    poisoned = copy.deepcopy(source)
    poisoned["checkpoints"][0]["facts"][0]["value"] = "GOLD-COPY-TRAP"
    poisoned["checkpoints"][0]["questions"][0]["expected"] = "abstain"
    assert project_scenario(source) == project_scenario(poisoned)
    assert execute(source)[0]["facts"] == execute(poisoned)[0]["facts"]


def test_provider_fixture_file_is_reproducible_from_inputs_without_gold_access():
    inputs = [project_scenario(s) for s in read_jsonl(CORPUS)]
    assert author_fixture_rows(inputs) == read_jsonl(CORPUS.with_name("provider_fixtures.jsonl"))


def test_actual_business_corruption_is_independently_detected_by_scorer():
    from dev.tools.memory_eval.evaluator import evaluate

    class CorruptingAdapter(DomainReplayAdapter):
        async def _checkpoint(self, scenario, checkpoint):
            item = next(iter(self.business_seed.values()))
            self.business.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            return await super()._checkpoint(scenario, checkpoint)

    source = scenario()
    observed = collect_observations([source], CorruptingAdapter(fixtures(source)))
    report = evaluate([source], observed, provenance={"provider_kind": "fake_provider"})
    assert report["zero_tolerance"]["business_damage"]["count"] == 1


def test_forbidden_network_attempt_cannot_be_swallowed_as_successful_replay(monkeypatch):
    from dev.tools.memory_eval.fixture_provider import FixtureProvider

    async def unexpected_network(*args):
        socket.getaddrinfo("must-never-resolve.example", 443)

    monkeypatch.setattr(FixtureProvider, "generate", unexpected_network)
    source = scenario()
    with pytest.raises(EvaluationInputError, match="network"):
        collect_observations([source], DomainReplayAdapter(fixtures(source)))


def test_direct_projected_input_rejects_hidden_labels_in_questions():
    source = scenario()
    projected = project_scenario(source)
    projected["checkpoints"][0]["questions"][0]["expected"] = "abstain"
    with pytest.raises(EvaluationInputError):
        DomainReplayAdapter(fixtures(source)).observe_scenario(projected)


@pytest.mark.parametrize("language", ["kk", "ru", "en", "mixed"])
@pytest.mark.parametrize("edit_text", ["", "I use Rust."])
def test_real_admin_confirmation_succeeds_and_edit_only_invalidates(language, edit_text):
    source = scenario(49, language)
    confirmed = source["events"][-1]
    source["events"].append(
        {
            **confirmed,
            "event_id": "edit-confirm",
            "type": "edit",
            "edited_at": confirmed["original_sent_at"] + 1,
            "text": edit_text,
        }
    )
    source["checkpoints"].append(
        {"checkpoint_id": "after-edit", "after_event": "edit-confirm", "facts": [], "questions": []}
    )
    _, before, after = execute(source)
    group = [fact for fact in before["facts"] if fact["subject_id"] == "group"]
    assert len(group) == 1 and group[0]["field"] == "rule"
    assert group[0]["evidence"]["source_event"] == "confirm"
    assert before["replay"]["events"][-1]["status"] == "APPLIED"
    assert after["replay"]["events"][-1]["status"] == "INVALIDATED"
    assert not any(fact["subject_id"] == "group" or fact["value"] == "Rust" for fact in after["facts"])
    assert [{key: value for key, value in row.items() if key != "age_seconds"} for row in after["traces"]["work"]] == [
        {key: value for key, value in row.items() if key != "age_seconds"} for row in before["traces"]["work"]
    ]
    assert after["traces"]["safety_surfaces"]["raw"] == before["traces"]["safety_surfaces"]["raw"]


def test_admin_domain_protocol_failure_is_not_swallowed_as_executed(monkeypatch):
    from services.memory_v2.models import MemoryInputError
    from services.memory_v2.writer import FactWriter

    def invalid_protocol(*args, **kwargs):
        raise MemoryInputError("Injected invalid confirmation protocol")

    monkeypatch.setattr(FactWriter, "confirm_group_fact", invalid_protocol)
    with pytest.raises(EvaluationInputError, match="admin_confirmation failed"):
        execute(scenario(49))


@pytest.mark.parametrize("operation", ["PutItem", "UpdateItem", "TransactWriteItems", "BatchWriteItem"])
def test_transient_successful_raw_writes_remain_visible_after_real_purge(operation):
    from dev.tools.memory_eval.evaluator import evaluate

    secret = "SYNTHETIC-SECRET-RAW-LEAK"
    source = with_events(
        {
            "type": "message",
            "message_id": "13",
            "text": "My password is " + secret,
            "original_sent_at": 2_000_000_004,
            "edited_at": 0,
            "safe": False,
            "epoch": "synthetic-epoch-1",
            "source_version": 1,
        },
        {"type": "forget_group"},
    )
    source["sensitive_markers"] = [secret]

    class LeakingAdapter(DomainReplayAdapter):
        async def _event(self, event):
            await super()._event(event)
            if event.get("message_id") != "13":
                return
            item = {"pk": "CHAT#" + event["chat_id"], "sk": "RAW#13", "kind": "RAW", "text": secret}
            table, client = self.repo.table, self.repo.table.meta.client
            if operation == "PutItem":
                table.put_item(Item=item)
            elif operation == "UpdateItem":
                table.update_item(
                    Key={"pk": item["pk"], "sk": item["sk"]},
                    UpdateExpression="SET #text = :text, kind = :kind",
                    ExpressionAttributeNames={"#text": "text"},
                    ExpressionAttributeValues={":text": secret, ":kind": "RAW"},
                )
            elif operation == "TransactWriteItems":
                client.transact_write_items(TransactItems=[{"Put": {"TableName": table.name, "Item": item}}])
            else:
                client.batch_write_item(RequestItems={table.name: [{"PutRequest": {"Item": item}}]})

        async def _checkpoint(self, scenario, checkpoint):
            if checkpoint["checkpoint_id"] == "after":
                assert not list(self.repo._list(self.chats[0], "RAW#"))
            return await super()._checkpoint(scenario, checkpoint)

    catalog = FixtureCatalog(author_fixture_rows([project_scenario(source)]))
    observed = collect_observations([source], LeakingAdapter(catalog))
    assert secret in observed[-1]["traces"]["safety_surfaces"]["raw"]
    report = evaluate([source], observed, provenance={"provider_kind": "fake_provider"})
    assert report["zero_tolerance"]["sensitive_leak"]["count"] == 1


def test_execution_source_fingerprint_covers_budget_shared_tool_and_lock(tmp_path):
    from dev.tools.memory_eval.__main__ import source_provenance

    paths = (
        "src/bot/services/memory_budget.py",
        "src/bot/services/memory_safety.py",
        "src/shared/python/zerde_common/dynamodb.py",
        "dev/tools/memory_eval/domain_adapter.py",
        "pyproject.toml",
        "uv.lock",
    )
    for name in paths:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("first")
    previous = source_provenance(tmp_path)
    for name in paths:
        (tmp_path / name).write_text("changed")
        current = source_provenance(tmp_path)
        assert current["execution_source_sha256"] != previous["execution_source_sha256"]
        assert current["execution_source_files"] == len(paths)
        previous = current


def test_unverified_synthetic_aws_measurement_cannot_bypass_real_budget_gate(monkeypatch):
    from services.memory_v2._cost_state import CostState

    original = CostState.record_measurement

    def unverified(self, *args, **kwargs):
        return original(self, *args, **{**kwargs, "verified": False})

    monkeypatch.setattr(CostState, "record_measurement", unverified)
    observed = execute(scenario())[0]
    assert observed["facts"] == []
    assert observed["answers"] == []
    assert observed["traces"]["budget_ledger"]["model"] == {}
    assert observed["traces"]["safety_surfaces"]["context"] == []
    assert all(row["state"] == "PAUSED" for row in observed["traces"]["work"])
