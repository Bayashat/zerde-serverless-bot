"""Offline evaluator fault injection. Oracle/fake-provider results are not model quality evidence."""

import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dev.tools.memory_eval.contract import EvaluationInputError, read_jsonl, validate_corpus
from dev.tools.memory_eval.corpus_authoring import build_corpus
from dev.tools.memory_eval.evaluator import evaluate
from dev.tools.memory_eval.reporting import render_catalog, render_report
from dev.tools.memory_eval.runner import OracleSelfCheck, collect_observations

FIXTURES = Path(__file__).parent / "fixtures" / "memory_v2_eval"


@pytest.fixture
def corpus():
    return read_jsonl(FIXTURES / "scenarios.jsonl")


def selected(corpus, title=None):
    return [next(case for case in corpus if case["language"] == "en" and (title is None or case["title"] == title))]


def oracle(corpus):
    return collect_observations(corpus, OracleSelfCheck())


def test_corpus_size_real_multiturn_language_slices_and_reproducible_catalog(corpus):
    info = validate_corpus(corpus)
    assert info["totals"] == {"scenarios": 240, "gold_facts": 516, "unknown_questions": 256}
    assert info["size_gate"] and info["unique_conversations"] == 240
    assert {row["scenarios"] for row in info["languages"].values()} == {60}
    assert info["independent_review"] == "PENDING"
    assert corpus == build_corpus()
    assert (FIXTURES / "CATALOG.md").read_text() == render_catalog(corpus)
    assert len({case["title"] for case in corpus}) == 60
    assert all(len(case["events"]) >= 3 for case in corpus)
    assert {case["authorship"] for case in corpus} == {"ai_authored"}


def test_oracle_checks_bookkeeping_but_never_claims_model_dev_or_real_group_pass(corpus):
    report = evaluate(corpus, oracle(corpus), provenance={"provider_kind": "synthetic_oracle"})
    assert report["numeric_thresholds_pass"] and report["complete"]
    assert report["overall"]["precision"] == report["overall"]["recall"] == 1
    assert all(row["source_support"] == row["unknown_abstention"] == 1 for row in report["languages"].values())
    assert report["product_gate"] == "IMPLEMENTED_UNPROVEN" and report["model_quality_claim"] == "NOT_VERIFIED"
    assert report["dev_canary"] == report["production_pilot"]["status"] == "NOT_RUN"
    assert all(row["status"] == "UNVERIFIED" for row in report["latency"].values())
    assert report["cost"]["status"] == "NOT_PROVIDED"
    assert "synthetic_oracle" in render_report(report) and "NOT_VERIFIED" in render_report(report)


def test_missing_cases_and_missing_questions_do_not_count_as_successful_abstentions(corpus):
    small = selected(corpus)
    missing = evaluate(small, [])
    assert missing["overall"]["fn"] == 2 and missing["overall"]["unknown_abstention"] == 0
    assert missing["overall"]["supported_questions"] == 1
    assert missing["overall"]["supported_answer_recall"] == 0
    assert not missing["complete"]
    assert all(row["status"] == "UNVERIFIED" for row in missing["zero_tolerance"].values())
    observations = oracle(small)
    observations[0]["answers"] = []
    report = evaluate(small, observations)
    assert not report["complete"] and report["overall"]["missing_answers"] == 2
    assert report["overall"]["unknown_abstained"] == 0


def test_precision_recall_have_exact_denominators_and_duplicate_fact_is_false_positive(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["facts"].append(copy.deepcopy(observations[0]["facts"][0]))
    observations[0]["facts"].pop(1)
    report = evaluate(small, observations)
    assert (report["overall"]["tp"], report["overall"]["fp"], report["overall"]["fn"]) == (1, 1, 1)
    assert report["overall"]["precision"] == report["overall"]["recall"] == 0.5


def test_bad_language_slice_is_not_hidden_by_aggregate(corpus):
    observations = oracle(corpus)
    for row in observations:
        if row["scenario_id"].startswith("kk-"):
            row["facts"] = []
    report = evaluate(corpus, observations)
    assert report["languages"]["kk"]["recall"] == 0
    assert report["languages"]["en"]["thresholds_pass"]
    assert not report["numeric_thresholds_pass"]


@pytest.mark.parametrize(
    "field,value,gate", [("subject_id", "999", "wrong_identity"), ("chat_id", "-888", "cross_chat")]
)
def test_identity_and_group_errors_derived_from_source_not_self_report(corpus, field, value, gate):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["facts"][0][field] = value
    observations[0]["violations"] = {gate: 0}
    report = evaluate(small, observations)
    assert report["zero_tolerance"][gate]["count"] == 1
    assert report["zero_tolerance"][gate]["status"] == "FAIL"


@pytest.mark.parametrize(
    "title",
    [
        "old_task_replay_after_forget",
        "old_epoch_replay",
        "empty_source_edit",
        "learning_pause_does_not_hide_edit",
        "delete_one_source_preserves_business",
        "forget_group_preserves_other_chat",
    ],
)
def test_old_source_resurrection_derived_from_operations(corpus, title):
    small = selected(corpus, title)
    observations = oracle(small)
    observations[-1]["facts"].append(copy.deepcopy(observations[0]["facts"][0]))
    report = evaluate(small, observations)
    assert report["zero_tolerance"]["delete_resurrection"]["status"] == "FAIL"


def test_optout_future_source_is_still_invalid_but_optin_new_message_is_valid(corpus):
    small = selected(corpus, "optout_future_message")
    observations = oracle(small)
    fresh = small[0]["events"][-1]
    observations[-1]["facts"].append(
        {
            "chat_id": fresh["chat_id"],
            "subject_id": fresh["user_id"],
            "field": "tech_stack",
            "value": "Elixir",
            "evidence": {"source_event": fresh["event_id"], "start": 0, "end": len(fresh["text"])},
        }
    )
    assert evaluate(small, observations)["zero_tolerance"]["delete_resurrection"]["status"] == "FAIL"
    valid = selected(corpus, "optout_then_explicit_optin_new_source")
    assert evaluate(valid, oracle(valid))["zero_tolerance"]["delete_resurrection"]["status"] == "PASS"


def test_sensitive_source_is_detected_even_when_output_value_looks_public(corpus):
    small = selected(corpus, "salary_and_account_safety")
    observations = oracle(small)
    original = observations[-1]["facts"][0]
    unsafe = next(event for event in small[0]["events"] if event.get("safe") is False)
    original["evidence"] = {"source_event": unsafe["event_id"], "start": 0, "end": len(unsafe["text"])}
    report = evaluate(small, observations)
    assert report["zero_tolerance"]["sensitive_leak"]["status"] == "FAIL"
    assert report["overall"]["source_support"] < 1


def test_secret_value_detected_independently_of_claimed_source_safety(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["facts"][0]["value"] = "SYNTHETIC-SECRET-ONLY"
    assert evaluate(small, observations)["zero_tolerance"]["sensitive_leak"]["count"] == 1


def test_missing_source_or_business_or_action_trace_is_unverified_not_zero(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["facts"][0]["evidence"]["source_event"] = "absent"
    observations[0].pop("traces")
    report = evaluate(small, observations)
    assert report["overall"]["source_support"] < 1
    assert all(row["status"] == "UNVERIFIED" for row in report["zero_tolerance"].values())
    assert report["coverage"]["status"] == "UNVERIFIED"


@pytest.mark.parametrize("protected", ["CONTEST#23", "SETTINGS", "CONTEST_TTL_OUTBOX"])
def test_business_damage_compares_exact_protected_snapshots(corpus, protected):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["traces"]["business_after"] = {**small[0]["protected_business"], protected: "modified"}
    assert evaluate(small, observations)["zero_tolerance"]["business_damage"]["count"] == 1


def test_proactive_actions_are_counted_without_prediction_violation_claim(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["traces"]["sent_actions"] = [{"kind": "reaction"}, {"kind": "explicit_answer"}]
    assert evaluate(small, observations)["zero_tolerance"]["automatic_social"]["count"] == 1


def test_unknown_answer_with_assertion_is_not_abstention_even_if_flag_says_true(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["answers"][-1]["assertions"] = [copy.deepcopy(observations[0]["facts"][0])]
    report = evaluate(small, observations)
    assert report["overall"]["unknown_abstention"] == 0
    assert report["overall"]["source_support"] < 1  # Known fact does not answer this unknown question.


def test_answering_for_other_target_is_detected_even_with_valid_fact_source(corpus):
    small = selected(corpus, "same_name_different_id")
    observations = oracle(small)
    observations[-1]["answers"][0]["assertions"] = [copy.deepcopy(observations[-1]["facts"][-1])]
    assert evaluate(small, observations)["zero_tolerance"]["wrong_identity"]["status"] == "FAIL"


def test_supported_questions_cannot_silently_disappear_from_answer_metrics(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["answers"][0] = {**observations[0]["answers"][0], "abstained": True, "assertions": []}
    report = evaluate(small, observations)
    assert report["overall"]["supported_questions"] == 1
    assert report["overall"]["supported_answer_recall"] == 0


def test_stale_last_confirmed_is_not_scored_as_current_truth(corpus):
    small = selected(corpus, "stale_city_requires_last_confirmed")
    observations = oracle(small)
    observations[-1]["facts"][0].pop("temporal_status")
    report = evaluate(small, observations)
    assert report["overall"]["fp"] == 1 and report["overall"]["fn"] == 1


def test_paused_expired_and_failed_work_do_not_fake_success_or_zero_latency(corpus):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["traces"]["work"] = [
        {"work_id": "pause", "state": "PAUSED", "lane": "normal", "elapsed_seconds": 0, "age_seconds": 900},
        {"work_id": "expire", "state": "EXPIRED", "lane": "normal", "elapsed_seconds": 0},
        {"work_id": "fail", "state": "FAILED"},
        {"work_id": "ok", "state": "DONE", "lane": "normal", "elapsed_seconds": 301},
        {"work_id": "recover", "state": "DONE", "lane": "recovery", "elapsed_seconds": 599},
    ]
    observations[0]["traces"]["ask_text_seconds"] = 16
    report = evaluate(small, observations)
    assert report["coverage"]["states"] == {"paused": 1, "expired": 1, "failed": 1, "done": 2}
    assert report["coverage"]["pending_max_age_seconds"] == 900
    assert report["latency"]["normal"] == {"samples": 1, "p95_seconds": 301, "limit_seconds": 300, "status": "FAIL"}
    assert report["latency"]["recovery"]["status"] == "PASS"
    assert report["latency"]["ask_text"]["status"] == "FAIL"


def test_work_snapshot_is_counted_once_at_latest_checkpoint(corpus):
    small = selected(corpus, "provider_recovery_commits_pending_once")
    observations = oracle(small)
    observations[1]["traces"]["work"] = [{"work_id": "same", "state": "PENDING", "age_seconds": 80}]
    observations[-1]["traces"]["work"] = [
        {"work_id": "same", "state": "DONE", "lane": "recovery", "elapsed_seconds": 100}
    ]
    report = evaluate(small, observations)
    assert report["coverage"]["distinct_work"] == 1 and report["coverage"]["states"] == {"done": 1}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, True])
def test_invalid_latency_and_cost_are_rejected(corpus, bad):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["traces"]["ask_text_seconds"] = bad
    with pytest.raises(EvaluationInputError):
        evaluate(small, observations)
    observations[0]["traces"].pop("ask_text_seconds")
    observations[0]["traces"]["cost"] = {"usd": bad}
    with pytest.raises(EvaluationInputError):
        evaluate(small, observations)


@pytest.mark.parametrize("line", ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', "[]"])
def test_json_input_rejects_ambiguous_or_nonfinite_records(tmp_path, line):
    path = tmp_path / "bad.jsonl"
    path.write_text(line)
    with pytest.raises(EvaluationInputError):
        read_jsonl(path)


def test_corpus_rejects_future_evidence_and_empty_business_contract(corpus):
    small = selected(corpus, "new_source_edit")
    small[0]["checkpoints"][0]["facts"][0]["evidence"]["source_event"] = "edit1"
    with pytest.raises(EvaluationInputError, match="future"):
        validate_corpus(small)
    small = selected(corpus)
    small[0]["protected_business"] = {}
    with pytest.raises(EvaluationInputError, match="business"):
        validate_corpus(small)


def test_duplicate_predictions_and_unknown_question_ids_fail_instead_of_overwriting(corpus):
    small = selected(corpus)
    observations = oracle(small)
    with pytest.raises(EvaluationInputError, match="Duplicate"):
        evaluate(small, observations + observations)
    observations[0]["answers"][0]["question_id"] = "foreign"
    with pytest.raises(EvaluationInputError, match="unknown answer"):
        evaluate(small, observations)


def test_actual_extractor_with_fake_provider_hallucination_is_caught_without_oracle(monkeypatch, corpus):
    from services.memory_v2.extractor import MemoryExtractor
    from services.memory_v2.models import ExtractionSource, SourceRef

    def forbidden_network(*args, **kwargs):
        raise AssertionError("Offline evaluation must not open network")

    monkeypatch.setattr("socket.create_connection", forbidden_network)
    small = selected(corpus)
    event = small[0]["events"][0]
    # Deliberately wrong semantics, but a valid structured schema and real source excerpt.
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "sources": [
                                            {
                                                "source_index": 0,
                                                "facts": [
                                                    {
                                                        "field": "occupation",
                                                        "value": "pilot",
                                                        "evidence": event["text"],
                                                        "facet": "",
                                                        "action": "assert",
                                                        "attribution": "self_explicit",
                                                    }
                                                ],
                                            }
                                        ]
                                    }
                                )
                            }
                        ]
                    },
                }
            ]
        }
    )
    quota = MagicMock()
    quota.increment_and_check.return_value = (1, True)
    extractor = MemoryExtractor(provider=provider, budget=MagicMock(), validate_sources=AsyncMock(), rate_limit=quota)
    source = ExtractionSource(
        event["chat_id"],
        SourceRef(event["message_id"], 1, event["epoch"]),
        event["user_id"],
        event["text"],
        (),
        event["original_sent_at"],
    )
    result = asyncio.run(extractor.extract_batch([source]))[0]
    assert result.status == "complete" and provider.generate.await_count == 1
    change = result.changes[0]
    observations = [
        {
            "scenario_id": small[0]["scenario_id"],
            "checkpoint_id": "baseline",
            "facts": [
                {
                    "chat_id": source.chat_id,
                    "subject_id": source.actor_user_id,
                    "field": change.field,
                    "value": change.value,
                    "evidence": {
                        "source_event": event["event_id"],
                        "start": change.evidence.start,
                        "end": change.evidence.end,
                    },
                }
            ],
            "answers": [],
        }
    ]
    report = evaluate(small, observations, provenance={"provider_kind": "fake_provider"})
    assert report["overall"]["fp"] == 1 and report["overall"]["source_support"] == 0
    assert report["model_quality_claim"] == "NOT_VERIFIED" and not report["complete"]


@pytest.mark.parametrize("surface", ["raw", "context", "logs", "answers"])
def test_sensitive_captured_surfaces_are_checked_without_self_report(corpus, surface):
    small = selected(corpus)
    observations = oracle(small)
    observations[0]["traces"]["safety_surfaces"][surface] = ["prefix synthetic-secret-only suffix"]
    assert evaluate(small, observations)["zero_tolerance"]["sensitive_leak"]["status"] == "FAIL"
    observations[0]["traces"].pop("safety_surfaces")
    assert evaluate(small, observations)["zero_tolerance"]["sensitive_leak"]["status"] == "UNVERIFIED"
