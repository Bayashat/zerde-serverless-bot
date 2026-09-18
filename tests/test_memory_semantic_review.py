"""Synthetic bookkeeping/fault checks only; these are not real-model quality evidence."""

import copy
import fcntl
import json
import sqlite3
from pathlib import Path

import pytest

from dev.tools.memory_eval import semantic_review as review
from dev.tools.memory_eval.__main__ import source_provenance
from dev.tools.memory_eval.contract import EvaluationInputError, fingerprint, read_jsonl, validate_corpus
from dev.tools.memory_eval.evaluator import evaluate
from dev.tools.memory_eval.replay_input import project_scenario
from dev.tools.memory_eval.runner import OracleSelfCheck, collect_observations

FIXTURES = Path(__file__).parent / "fixtures/memory_v2_eval"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def corpus():
    return read_jsonl(FIXTURES / "scenarios.jsonl")


def subset(corpus, title="education_self_statement"):
    return [next(s for s in corpus if s["language"] == "en" and (s["title"] == title or s["scenario_id"] == title))]


def public_observations(corpus):
    """Construct explicit synthetic delivery evidence, never call a runtime/provider."""
    observations = collect_observations(corpus, OracleSelfCheck())
    attach_deliveries(corpus, observations)
    return observations


def attach_deliveries(corpus, observations):
    indexed = {(o["scenario_id"], o["checkpoint_id"]): o for o in observations}
    for scenario in corpus:
        sends, routes = [], []
        for cp in scenario["checkpoints"]:
            obs = indexed[(scenario["scenario_id"], cp["checkpoint_id"])]
            obs.setdefault("replay", {"state": "EXECUTED"})
            questions = {q["question_id"]: q for q in cp["questions"]}
            for answer in obs["answers"]:
                qid = answer["question_id"]
                question = questions[qid]
                mid = 1_000_000_000 + int(fingerprint(qid)[:12], 16) % 900_000_000
                texts = answer.setdefault("response_text", ["Synthetic test answer, not model output"])
                ids = [mid + 100 + i for i in range(len(texts))]
                delivery = {
                    "question_id": qid,
                    "route": "plain" if answer["abstained"] else "memory",
                    "state": "SENT",
                    "request_id": f"tg:{question['chat_id']}:{mid}",
                    "message_ids": ids,
                    "transport": "synthetic_telegram_sink_with_real_persistence",
                }
                answer["delivery"] = delivery
                routes.append(copy.deepcopy(delivery))
                sends.extend(
                    {"kind": "explicit_answer", "chat_id": question["chat_id"], "message_id": i, "text": t}
                    for i, t in zip(ids, texts)
                )
            obs["traces"].update(sent_actions=copy.deepcopy(sends), public_route=copy.deepcopy(routes))


def package(corpus, observations=None, *, registered=False):
    observations = public_observations(corpus) if observations is None else observations
    strict = evaluate(corpus, observations, provenance={"provider_kind": "synthetic_oracle"})
    rules = review.policy()
    bindings = {
        "policy": rules,
        "policy_sha256": fingerprint(rules),
        "corpus_json_sha256": fingerprint(corpus),
        "observations_json_sha256": fingerprint(observations),
        "strict_report_json_sha256": fingerprint(strict),
        "registration": {
            "mode": "SOURCE_BOUND_OPERATOR_REGISTERED" if registered else "RETROSPECTIVE_DIAGNOSTIC",
            "reviewer_ids": ["independent"],
            "implementation_author": "author",
        },
    }
    inventory = review.build_inventory(corpus, observations, bindings)
    return observations, strict, bindings, inventory


def decisions(inventory):
    """Oracle judgments test accounting only; no real semantic review is manufactured."""
    base = {
        "schema_version": 1,
        "policy_sha256": inventory["policy_sha256"],
        "inventory_sha256": fingerprint(inventory),
        "reviewer_id": "independent",
        "review_method": "independent_text_review",
        "reason": "synthetic_bookkeeping_test",
        "rationale": "Test fixture only; does not establish language equivalence or model quality.",
    }
    output, used = [], set()
    for expected in inventory["expected"]:
        actual = next(
            (
                a
                for a in inventory["actual"]
                if a["id"] not in used
                and a["key"][:4] == expected["key"][:4]
                and a["fact"].get("fact_id") == expected["fact"]["fact_id"]
            ),
            None,
        )
        if actual:
            used.add(actual["id"])
        output.append(
            {
                **base,
                "kind": "education",
                "expected_id": expected["id"],
                "expected_sha256": expected["sha256"],
                "actual_id": actual["id"] if actual else None,
                "actual_sha256": actual["sha256"] if actual else None,
                "qualification_checks": dict.fromkeys(review.QUALIFICATION_CHECKS, bool(actual)),
                "verdict": "SUPPORTED" if actual else "MISSING",
            }
        )
    for actual in inventory["actual"]:
        if actual["id"] not in used:
            output.append(
                {
                    **base,
                    "kind": "education",
                    "expected_id": None,
                    "expected_sha256": None,
                    "actual_id": actual["id"],
                    "actual_sha256": actual["sha256"],
                    "verdict": "UNEXPECTED",
                    "qualification_checks": dict.fromkeys(review.QUALIFICATION_CHECKS, False),
                }
            )
    for answer in inventory["answers"]:
        output.append(
            {
                **base,
                "kind": "answer",
                "answer_id": answer["id"],
                "answer_sha256": answer["sha256"],
                "verdict": "MISSING" if answer["answer"] is None else "CONFIRMED",
                "zero_tolerance_findings": [],
            }
        )
    return output


def verified(corpus, package, rows=None):
    observations, strict, bindings, inventory = package
    return review.verify_review(
        corpus, observations, strict, inventory, decisions(inventory) if rows is None else rows, bindings=bindings
    )


def test_inventory_keeps_every_language_checkpoint_and_all_answer_bodies(corpus):
    bundle = package(corpus)
    inventory = bundle[3]
    assert len(inventory["expected"]) == len(inventory["actual"]) == 112
    assert len(inventory["answers"]) == 480
    assert {tuple(sorted(c.items())) for c in inventory["denominators"].values()} == {
        tuple(
            sorted(
                {
                    "scenarios": 60,
                    "checkpoints": 101,
                    "gold_profile": 191,
                    "known": 56,
                    "unknown": 64,
                    "expected_education_profile": 18,
                    "actual_education_profile": 18,
                    "expected_education_answer": 10,
                    "actual_education_answer": 10,
                }.items()
            )
        )
    }
    report = verified(corpus, bundle)
    assert report["complete"] and report["semantic_review_gates_pass"]
    assert report["status"] == "RETROSPECTIVE_DIAGNOSTIC" and not report["production_ready"]
    assert report["overall"] == bundle[1]["overall"]
    assert report["runtime_source_revision_epoch"] == "NOT_RECORDED"
    assert report["budget_pause_no_memory_forwarding"] == "NOT_VERIFIED_BY_THIS_TOOL"


def test_qualification_wording_adjusts_only_its_own_education_occurrences(corpus):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    for row in obs:
        for fact in row["facts"]:
            if fact["field"] == "education":
                fact["value"] = "Synthetic alternative qualification wording"
    bundle = package(small, obs)
    strict_before = copy.deepcopy(bundle[1])
    report = verified(small, bundle)
    assert report["overall"]["tp"] > bundle[1]["overall"]["tp"]
    assert report["overall"]["supported_answers_complete"] == bundle[1]["overall"]["supported_answers_complete"]
    assert report["overall"]["gold_observations"] == bundle[1]["overall"]["gold_observations"]
    assert bundle[1] == strict_before
    assert {r["surface"] for r in report["adjustments_by_occurrence"]} == {"profile"}


def test_strict_correct_education_is_not_exempt_from_review(corpus):
    small = subset(corpus, "en-008")
    bundle = package(small, registered=True)
    rows = decisions(bundle[3])
    missing = next(row for row in rows if row["kind"] == "education")
    rows.remove(missing)
    result = verified(small, bundle, rows)
    assert not result["complete"] and result["status"] == "INCOMPLETE"
    assert result["missing_reviews"]["actual"] == [missing["actual_id"]]


@pytest.mark.parametrize("check", review.QUALIFICATION_CHECKS)
def test_supported_requires_every_qualification_dimension(corpus, check):
    small = subset(corpus, "en-008")
    bundle = package(small)
    rows = decisions(bundle[3])
    next(r for r in rows if r["kind"] == "education")["qualification_checks"][check] = False
    with pytest.raises(EvaluationInputError, match="every check"):
        verified(small, bundle, rows)


@pytest.mark.parametrize("mutation", ["duplicate", "cross_surface", "hash", "policy", "reviewer", "model_review"])
def test_occurrence_bindings_and_independence_fail_closed(corpus, mutation):
    small = subset(corpus, "en-008")
    bundle = package(small, registered=True)
    rows = decisions(bundle[3])
    item = next(r for r in rows if r["kind"] == "education")
    if mutation == "duplicate":
        rows.append(copy.deepcopy(item))
    elif mutation == "cross_surface":
        other = next(r for r in rows if r["kind"] == "education" and r["actual_id"] != item["actual_id"])
        item["actual_id"], other["actual_id"] = other["actual_id"], item["actual_id"]
        item["actual_sha256"], other["actual_sha256"] = other["actual_sha256"], item["actual_sha256"]
    elif mutation == "hash":
        item["actual_sha256"] = "0" * 64
    elif mutation == "policy":
        item["policy_sha256"] = "0" * 64
    elif mutation == "reviewer":
        item["reviewer_id"] = "author"
    else:
        item["review_method"] = "MODEL_OBSERVED"
    with pytest.raises(EvaluationInputError):
        verified(small, bundle, rows)


def test_extra_education_stays_false_positive_and_unmatched(corpus):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    edu = next(f for f in obs[0]["facts"] if f["field"] == "education")
    obs[0]["facts"].append(copy.deepcopy(edu))
    bundle = package(small, obs)
    result = verified(small, bundle)
    assert result["overall"]["fp"] == 1
    assert result["overall"]["supported_assertions"] == result["overall"]["assertions"] - 1
    assert not result["semantic_review_gates_pass"]


def test_four_budget_paused_known_answers_stay_in_denominator(corpus):
    obs = public_observations(corpus)
    for row in obs:
        if row["scenario_id"].endswith("-033"):
            for answer in row["answers"]:
                answer.update(assertions=[], abstained=True)
    bundle = package(corpus, obs)
    result = verified(corpus, bundle)
    assert len(bundle[3]["expected"]) == 112 and len(bundle[3]["actual"]) == 108
    assert result["overall"]["supported_answers_complete"] == 220
    assert all(
        r["supported_questions"] == 56 and r["supported_answers_complete"] == 55 for r in result["languages"].values()
    )


@pytest.mark.parametrize("expected", ["abstain", "supported"])
def test_full_text_rejection_blocks_even_when_model_audit_misses_new_claim(corpus, expected):
    bundle = package(corpus, registered=True)
    rows = decisions(bundle[3])
    entry = next(a for a in bundle[3]["answers"] if a["question"]["expected"] == expected)
    row = next(r for r in rows if r.get("answer_id") == entry["id"])
    row.update(verdict="UNSUPPORTED", reason="unreported_personal_claim")
    result = verified(corpus, bundle, rows)
    metric = "unknown_abstained" if expected == "abstain" else "supported_answers_complete"
    assert result["overall"][metric] == bundle[1]["overall"][metric] - 1
    assert result["overall"]["assertions"] == bundle[1]["overall"]["assertions"]
    assert result["status"] == "FAIL" and result["manual_unsupported_answers"] == [entry["id"]]
    assert not result["semantic_review_gates_pass"]


@pytest.mark.parametrize("kind", ["education", "answer"])
def test_unresolved_reviews_cannot_pass(corpus, kind):
    bundle = package(subset(corpus, "en-008"), registered=True)
    rows = decisions(bundle[3])
    next(r for r in rows if r["kind"] == kind)["verdict"] = "UNRESOLVED"
    result = verified(subset(corpus, "en-008"), bundle, rows)
    assert not result["complete"] and result["status"] == "INCOMPLETE"


def test_manual_zero_gate_adds_block_without_overwriting_strict_gate(corpus):
    bundle = package(corpus, registered=True)
    rows = decisions(bundle[3])
    next(r for r in rows if r["kind"] == "answer").update(
        verdict="UNSUPPORTED", zero_tolerance_findings=["wrong_identity"]
    )
    result = verified(corpus, bundle, rows)
    assert result["manual_zero_tolerance_findings"] == {"wrong_identity": 1}
    assert result["inherited_zero_tolerance"]["wrong_identity"] == bundle[1]["zero_tolerance"]["wrong_identity"]
    assert result["status"] == "FAIL"


@pytest.mark.parametrize("mutation", ["orphan", "text", "request", "route", "reused", "prefix", "send_order"])
def test_cumulative_delivery_requires_exact_new_send_bijection(corpus, mutation):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    row = next(o for o in obs if o["answers"])
    if mutation == "orphan":
        row["traces"]["sent_actions"].append(
            {"kind": "explicit_answer", "chat_id": "-1", "message_id": 5, "text": "extra"}
        )
    elif mutation == "text":
        row["answers"][0]["response_text"][0] = "different"
    elif mutation == "request":
        row["answers"][0]["delivery"]["request_id"] = "tg:wrong:1"
    elif mutation == "route":
        row["traces"]["public_route"] = []
    elif mutation == "reused":
        row["answers"][1]["delivery"]["message_ids"] = row["answers"][0]["delivery"]["message_ids"]
        row["traces"]["public_route"][1] = copy.deepcopy(row["answers"][1]["delivery"])
    elif mutation == "prefix":
        small = subset(corpus, "en-033")
        obs = public_observations(small)
        assert len(obs) > 1
        obs[-1]["traces"]["sent_actions"] = []
    else:
        row["answers"][0]["response_text"] = ["one", "two"]
        attach_deliveries(small, obs)
        row["traces"]["sent_actions"][:2] = reversed(row["traces"]["sent_actions"][:2])
    with pytest.raises(EvaluationInputError):
        package(small, obs)


@pytest.mark.parametrize(
    "mutation",
    ["identity", "chat", "source", "cropped", "temporal", "quoted", "unsafe", "forwarded", "bot", "before_start"],
)
def test_human_supported_cannot_override_mechanical_source_gates(corpus, mutation):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    fact = next(f for f in obs[0]["facts"] if f["field"] == "education")
    source = next(e for e in small[0]["events"] if e["event_id"] == fact["evidence"]["source_event"])
    if mutation == "identity":
        fact["subject_id"] = "999"
    elif mutation == "chat":
        fact["chat_id"] = "-999"
    elif mutation == "source":
        fact["evidence"]["source_event"] = "absent"
    elif mutation == "cropped":
        fact["evidence"]["end"] -= 1
    elif mutation == "temporal":
        fact["temporal_status"] = "last_confirmed"
    elif mutation == "quoted":
        source["quoted_spans"] = [[0, len(source["text"])]]
    elif mutation == "unsafe":
        source["safe"] = False
    elif mutation == "before_start":
        source["original_sent_at"] = small[0]["learning_started_at"] - 1
    else:
        source["is_bot" if mutation == "bot" else mutation] = True
    if mutation in {"quoted", "unsafe", "forwarded", "bot"}:
        with pytest.raises(EvaluationInputError, match="Ineligible gold source"):
            package(small, obs)
        return
    bundle = package(small, obs)
    result = verified(small, bundle)
    assert result["mechanical_failures"] and not result["semantic_review_gates_pass"]


def test_non_education_cannot_gain_from_semantic_review(corpus):
    small = subset(corpus, "en-001")
    obs = public_observations(small)
    obs[0]["facts"][0]["value"] = "Unrelated ungrounded value"
    bundle = package(small, obs)
    result = verified(small, bundle)
    assert result["overall"] == bundle[1]["overall"]


def test_missing_answer_is_retained_and_cannot_be_confirmed(corpus):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    obs[0]["answers"].pop()
    attach_deliveries(small, obs)
    bundle = package(small, obs)
    assert len(bundle[3]["answers"]) == 2
    result = verified(small, bundle)
    assert not result["complete"] and result["overall"]["missing_answers"] == 1
    rows = decisions(bundle[3])
    next(r for r in rows if r["verdict"] == "MISSING" and r["kind"] == "answer")["verdict"] = "CONFIRMED"
    with pytest.raises(EvaluationInputError, match="actual absence"):
        verified(small, bundle, rows)


def write_json(path, value):
    path.write_text(json.dumps(value))


@pytest.fixture
def disk_run(tmp_path, corpus):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    root = inputs / "source"
    for scope in ("src/bot", "src/shared/python", "dev/tools/memory_eval"):
        (root / scope).mkdir(parents=True)
    for name in ("semantic_review.py", "evaluator.py", "contract.py"):
        (root / "dev/tools/memory_eval" / name).write_bytes((ROOT / "dev/tools/memory_eval" / name).read_bytes())
    for name in ("pyproject.toml", "uv.lock"):
        (root / name).write_text("# Synthetic file binding fixture\n")
    (root / "src/bot/main.py").write_text("# Synthetic, never executed\n")
    source = source_provenance(root)
    small = subset(corpus, "en-008")
    corpus_path = inputs / "corpus.jsonl"
    corpus_path.write_text("".join(json.dumps(s) + "\n" for s in small))
    observations = public_observations(small)
    info = validate_corpus(small)
    manifest = {
        "answer_route": "public-v1",
        "scenario_ids": [s["scenario_id"] for s in small],
        "corpus_sha256": info["sha256"],
        "input_sha256": fingerprint([project_scenario(s) for s in small]),
        "execution_source_sha256": source["execution_source_sha256"],
    }
    execution = {
        "scenario_id": small[0]["scenario_id"],
        "input_sha256": fingerprint(project_scenario(small[0])),
        "status": "EXECUTED",
    }
    provenance = {
        **manifest,
        "provider_kind": "recorded_provider",
        "planned_scenarios": 1,
        "completed_scenarios": 1,
        "execution_status": {"state": "FINISHED", "completed_scenarios": 1, "planned_scenarios": 1},
        "scenario_executions": [execution],
    }
    run = inputs / "run"
    run.mkdir()
    (run / "scenarios").mkdir()
    (run / "session.lock").touch()
    for name, value in (
        ("session.json", manifest),
        ("provenance.json", provenance),
        ("execution-status.json", {"state": "FINISHED", "completed_scenarios": 1, "planned_scenarios": 1}),
        ("report.json", evaluate(small, observations, provenance=provenance)),
    ):
        write_json(run / name, value)
    (run / "observations.jsonl").write_text("".join(json.dumps(o) + "\n" for o in observations))
    write_json(
        run / "scenarios" / (fingerprint(small[0]["scenario_id"]) + ".json"),
        {
            "scenario_id": small[0]["scenario_id"],
            "input_sha256": fingerprint(project_scenario(small[0])),
            "status": "EXECUTED",
            "observations": observations,
        },
    )
    with sqlite3.connect(run / "attempts.sqlite3") as db:
        db.execute("CREATE TABLE config (id INTEGER, fingerprint TEXT)")
        db.execute("INSERT INTO config VALUES (1, ?)", (fingerprint(manifest),))
        db.execute("CREATE TABLE attempts (started_at REAL)")
        db.execute("INSERT INTO attempts VALUES (1000.0)")
    registration = {
        "schema_version": 1,
        "policy_sha256": fingerprint(review.policy()),
        "manifest_sha256": fingerprint(manifest),
        "corpus_file_sha256": review._sha(corpus_path.read_bytes()),
        "execution_source_sha256": source["execution_source_sha256"],
        "reviewer_ids": ["independent"],
        "implementation_author": "author",
        "approved_at": 999.0,
        "approval_reference": "synthetic-test-only",
    }
    registration_path = inputs / "registration.json"
    write_json(registration_path, registration)
    return corpus_path, run, root, registration_path


def hashes(directory):
    return {str(p.relative_to(directory)): review._sha(p.read_bytes()) for p in directory.rglob("*") if p.is_file()}


def test_finished_run_registration_and_cli_leave_original_bytes_unchanged(disk_run, tmp_path):
    corpus, run, root, registration = disk_run
    before = hashes(tmp_path / "inputs")
    loaded = review.load_run(corpus, run, root, registration_path=registration)
    assert loaded.bindings["registration"]["mode"] == "SOURCE_BOUND_OPERATOR_REGISTERED"
    output = tmp_path / "review-inventory"
    assert (
        review.main(
            [
                "inventory",
                "--corpus",
                str(corpus),
                "--run-dir",
                str(run),
                "--execution-root",
                str(root),
                "--registration",
                str(registration),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert (output / "inventory.json").exists() and output.stat().st_mode & 0o777 == 0o700
    assert (output / "inventory.json").stat().st_mode & 0o777 == 0o600
    assert hashes(tmp_path / "inputs") == before


@pytest.mark.parametrize(
    "mutation",
    ["unfinished", "extra_scenario", "strict_score", "source", "manifest", "late_approval", "author", "ledger", "wal"],
)
def test_finished_bundle_tampering_or_unregistered_execution_rejected(disk_run, mutation):
    corpus, run, root, registration = disk_run
    if mutation == "unfinished":
        write_json(run / "execution-status.json", {"state": "RUNNING"})
    elif mutation == "extra_scenario":
        write_json(run / "scenarios/extra.json", {})
    elif mutation == "strict_score":
        report = json.loads((run / "report.json").read_text())
        report["overall"]["tp"] += 1
        write_json(run / "report.json", report)
    elif mutation == "source":
        (root / "src/bot/main.py").write_text("# changed\n")
    elif mutation == "manifest":
        data = json.loads((run / "session.json").read_text())
        data["input_sha256"] = "wrong"
        write_json(run / "session.json", data)
    elif mutation in {"late_approval", "author"}:
        data = json.loads(registration.read_text())
        data["approved_at" if mutation == "late_approval" else "implementation_author"] = (
            1000.0 if mutation == "late_approval" else "independent"
        )
        write_json(registration, data)
    elif mutation == "ledger":
        with sqlite3.connect(run / "attempts.sqlite3") as db:
            db.execute("UPDATE config SET fingerprint = 'wrong'")
    else:
        (run / "attempts.sqlite3-wal").touch()
    with pytest.raises(EvaluationInputError):
        review.load_run(corpus, run, root, registration_path=registration)


def test_running_lock_and_symbolic_inputs_are_rejected(disk_run):
    corpus, run, root, _ = disk_run
    with (run / "session.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(EvaluationInputError, match="still running"):
            review.load_run(corpus, run, root)
    alias = corpus.with_name("alias.jsonl")
    alias.symlink_to(corpus)
    with pytest.raises(EvaluationInputError, match="Symbolic"):
        review.load_run(alias, run, root)


@pytest.mark.parametrize("raw", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'])
def test_strict_json_rejects_ambiguous_input(raw):
    with pytest.raises(EvaluationInputError):
        review._json(raw)


def test_outputs_cannot_overwrite_or_enter_input_directories(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    with pytest.raises(EvaluationInputError, match="outside"):
        review._write_output(inputs / "output", {"report.json": {}}, [inputs])
    target = tmp_path / "new"
    review._write_output(target, {"report.json": {"first": True}}, [inputs])
    with pytest.raises(FileExistsError):
        review._write_output(target, {"report.json": {"overwrite": True}}, [inputs])
    assert json.loads((target / "report.json").read_text()) == {"first": True}


def test_missing_answer_binds_not_sent_route_without_hiding_actual_sends(corpus):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    answer = obs[0]["answers"].pop()
    trace = obs[0]["traces"]["public_route"][-1]
    trace.update(state="NOT_SENT", message_ids=[])
    obs[0]["traces"]["sent_actions"].pop()
    bundle = package(small, obs)
    entry = next(a for a in bundle[3]["answers"] if a["key"][-1] == answer["question_id"])
    assert entry["answer"] is None and entry["delivery"]["delivery"]["state"] == "NOT_SENT"
    result = verified(small, bundle)
    assert result["overall"]["missing_answers"] == 1 and not result["complete"]
    trace["message_ids"] = [123]
    with pytest.raises(EvaluationInputError, match="cannot hide"):
        package(small, obs)


def test_send_message_identity_cannot_be_reused_across_checkpoints(corpus):
    small = subset(corpus, "en-008")
    second = copy.deepcopy(small[0]["checkpoints"][0])
    second["checkpoint_id"] = "second"
    for query in second["questions"]:
        query["question_id"] += "-second"
    small[0]["checkpoints"].append(second)
    obs = public_observations(small)
    first = next(o for o in obs if o["answers"])
    last = obs[-1]
    assert first is not last
    original = last["answers"][0]["delivery"]["message_ids"][0]
    reused = first["answers"][0]["delivery"]["message_ids"][0]
    last["answers"][0]["delivery"]["message_ids"] = [reused]
    for send in last["traces"]["sent_actions"]:
        if send["message_id"] == original:
            send["message_id"] = reused
    for route in last["traces"]["public_route"]:
        if route["question_id"] == last["answers"][0]["question_id"]:
            route["message_ids"] = [reused]
    with pytest.raises(EvaluationInputError, match="reused across"):
        package(small, obs)


@pytest.mark.parametrize("state", ["FAILED", "UNKNOWN", "RUNNING", None, []])
def test_failed_or_unknown_checkpoint_replay_cannot_inherit_old_scorer_pass(corpus, state):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    obs[0]["replay"]["state"] = state
    with pytest.raises(EvaluationInputError, match="checkpoint replay"):
        package(small, obs)


@pytest.mark.parametrize("mutation", ["scene_status", "replay_state", "provenance_status", "provenance_count"])
def test_loader_requires_all_execution_status_owners_to_agree(disk_run, mutation):
    corpus, run, root, _ = disk_run
    scenario_path = next((run / "scenarios").glob("*.json"))
    if mutation in {"scene_status", "replay_state"}:
        data = json.loads(scenario_path.read_text())
        if mutation == "scene_status":
            data["status"] = "UNSUPPORTED"
        else:
            data["observations"][0]["replay"]["state"] = "FAILED"
        write_json(scenario_path, data)
    else:
        data = json.loads((run / "provenance.json").read_text())
        if mutation == "provenance_status":
            data["scenario_executions"][0]["status"] = "UNSUPPORTED"
        else:
            data["completed_scenarios"] = 0
        write_json(run / "provenance.json", data)
    with pytest.raises(EvaluationInputError):
        review.load_run(corpus, run, root)


@pytest.mark.parametrize("kind", ["forget_user", "optout", "new_epoch", "edit"])
def test_education_cannot_override_invalidated_source_lifecycle(corpus, kind):
    # Synthetic corrupted observations with a stale gold entry: even a human
    # SUPPORTED attestation must preserve the original lifecycle zero gate.
    small = subset(corpus, "en-008")
    source = small[0]["events"][0]
    event = {"event_id": "invalidate", "type": kind, "chat_id": source["chat_id"], "user_id": source["user_id"]}
    if kind == "edit":
        event = {**copy.deepcopy(source), **event, "text": "A different statement", "source_version": 2}
    small[0]["events"].append(event)
    small[0]["checkpoints"][0]["after_event"] = "invalidate"
    bundle = package(small)
    result = verified(small, bundle)
    assert result["mechanical_failures"]
    assert result["inherited_zero_tolerance"]["delete_resurrection"]["status"] == "FAIL"
    assert not result["semantic_review_gates_pass"]


def test_oversized_and_sensitive_education_evidence_cannot_be_promoted(corpus):
    small = subset(corpus, "en-008")
    small[0]["events"][0]["text"] += " harmless filler" * 30
    obs = public_observations(small)
    fact = next(f for f in obs[0]["facts"] if f["field"] == "education")
    fact["evidence"]["end"] = len(small[0]["events"][0]["text"])
    fact["value"] = small[0]["sensitive_markers"][0]
    bundle = package(small, obs)
    result = verified(small, bundle)
    assert result["mechanical_failures"] and not result["semantic_review_gates_pass"]
    assert result["inherited_zero_tolerance"]["sensitive_leak"]["status"] == "FAIL"


def test_review_decisions_and_negative_adjustments_are_bound_in_report(corpus):
    small = subset(corpus, "en-008")
    bundle = package(small)
    rows = decisions(bundle[3])
    item = next(r for r in rows if r["kind"] == "education")
    item["verdict"] = "UNSUPPORTED"
    result = verified(small, bundle, rows)
    assert result["decisions_sha256"] == fingerprint(rows)
    change = next(c for c in result["adjustments_by_occurrence"] if c["actual_id"] == item["actual_id"])
    assert change["strict_source_supported"] and not change["semantic_source_supported"]
    assert change["decision_sha256"] == fingerprint(item)
    assert result["review_completeness_by_language"]["en"]["complete"]


def test_one_bad_language_cannot_be_hidden_by_aggregate(corpus):
    obs = public_observations(corpus)
    for row in obs:
        if row["scenario_id"].startswith("kk-"):
            row["facts"] = []
    bundle = package(corpus, obs, registered=True)
    result = verified(corpus, bundle)
    assert result["complete"] and result["status"] == "FAIL"
    assert result["languages"]["kk"]["recall"] == 0
    assert result["languages"]["en"]["thresholds_pass"]


def test_unsupported_checkpoint_remains_incomplete(corpus):
    small = subset(corpus, "en-008")
    obs = public_observations(small)
    obs[0]["replay"]["state"] = "UNSUPPORTED"
    result = verified(small, package(small, obs, registered=True))
    assert not result["complete"] and result["status"] == "INCOMPLETE"


def test_cli_verifier_binds_original_decision_bytes_and_never_overwrites_inputs(disk_run, tmp_path):
    corpus, run, root, registration = disk_run
    inventory_dir, decisions_dir = tmp_path / "inventory", tmp_path / "decisions"
    decisions_dir.mkdir()
    base_args = [
        "--corpus",
        str(corpus),
        "--run-dir",
        str(run),
        "--execution-root",
        str(root),
        "--registration",
        str(registration),
    ]
    review.main(["inventory", *base_args, "--output", str(inventory_dir)])
    inventory_path = inventory_dir / "inventory.json"
    inventory = json.loads(inventory_path.read_text())
    decision_path = decisions_dir / "judgments.jsonl"
    decision_path.write_text("".join(json.dumps(d) + "\n" for d in decisions(inventory)))
    before = hashes(tmp_path / "inputs")
    output = tmp_path / "report"
    code = review.main(
        [
            "verify",
            *base_args,
            "--inventory",
            str(inventory_path),
            "--decisions",
            str(decision_path),
            "--output",
            str(output),
        ]
    )
    report = json.loads((output / "report.json").read_text())
    assert code == 2  # One synthetic scenario is below the required corpus size.
    assert report["review_input_files"][str(decision_path)] == review._sha(decision_path.read_bytes())
    assert hashes(tmp_path / "inputs") == before


@pytest.mark.parametrize("mutation", ["id", "finding", "verdict", "row"])
def test_malformed_decisions_have_safe_input_errors(corpus, mutation):
    small = subset(corpus, "en-008")
    bundle = package(small)
    rows = decisions(bundle[3])
    if mutation == "row":
        rows[0] = []
    elif mutation == "id":
        rows[0]["actual_id"] = []
    elif mutation == "verdict":
        rows[0]["verdict"] = []
    else:
        next(r for r in rows if r["kind"] == "answer")["zero_tolerance_findings"] = [[]]
    with pytest.raises(EvaluationInputError):
        verified(small, bundle, rows)


def test_registration_cannot_be_backfilled_into_old_execution_source(disk_run):
    corpus, run, root, registration_path = disk_run
    (root / "dev/tools/memory_eval/semantic_review.py").unlink()
    source = source_provenance(root)
    manifest = json.loads((run / "session.json").read_text())
    manifest["execution_source_sha256"] = source["execution_source_sha256"]
    write_json(run / "session.json", manifest)
    provenance = json.loads((run / "provenance.json").read_text())
    provenance["execution_source_sha256"] = source["execution_source_sha256"]
    write_json(run / "provenance.json", provenance)
    observations = read_jsonl(run / "observations.jsonl")
    write_json(run / "report.json", evaluate(read_jsonl(corpus), observations, provenance=provenance))
    registration = json.loads(registration_path.read_text())
    registration.update(
        manifest_sha256=fingerprint(manifest), execution_source_sha256=source["execution_source_sha256"]
    )
    write_json(registration_path, registration)
    loaded = review.load_run(corpus, run, root)
    assert loaded.bindings["registration"]["mode"] == "RETROSPECTIVE_DIAGNOSTIC"
    with pytest.raises((EvaluationInputError, OSError)):
        review.load_run(corpus, run, root, registration_path=registration_path)
