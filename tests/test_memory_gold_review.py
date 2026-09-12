"""Frozen pre-provider label corrections; no model or network calls."""

import copy
import json
from pathlib import Path

import pytest

from dev.tools.memory_eval import corpus_authoring
from dev.tools.memory_eval.authoring_aliases import APPROVED_PROPOSAL_SHA256, accepted_values_for
from dev.tools.memory_eval.contract import read_jsonl
from dev.tools.memory_eval.domain_adapter import DomainReplayAdapter
from dev.tools.memory_eval.evaluator import _inspect_assertion, evaluate
from dev.tools.memory_eval.fixture_authoring import author_fixture_rows
from dev.tools.memory_eval.fixture_provider import FixtureCatalog
from dev.tools.memory_eval.replay_input import project_scenario
from dev.tools.memory_eval.runner import OracleSelfCheck, collect_observations

FIXTURES = Path(__file__).parent / "fixtures" / "memory_v2_eval"


@pytest.fixture(scope="module")
def corpus():
    return read_jsonl(FIXTURES / "scenarios.jsonl")


def inspect(scenario, checkpoint, assertion):
    sources = {event["event_id"]: event for event in scenario["events"] if "text" in event}
    return _inspect_assertion(assertion, checkpoint["facts"], sources, set(), scenario["sensitive_markers"])[1]


def test_every_approved_alias_is_supported_in_its_actual_source_scope(corpus):
    assert APPROVED_PROPOSAL_SHA256 == "a9cb0eb5412ae99560294fbf64a654475bd1037c1006d1b49cae44d7a30a3319"
    covered = set()
    for scenario in corpus:
        for checkpoint in scenario["checkpoints"]:
            for fact in checkpoint["facts"]:
                for alias in fact.get("accepted_values", []):
                    assertion = {**fact, "value": alias}
                    assert inspect(scenario, checkpoint, assertion)
                    covered.add((fact["field"], fact["facet"], fact["value"], alias))
    assert len(covered) == 58


def test_future_corpus_change_cannot_inherit_the_frozen_review(monkeypatch):
    assert all(row["independent_review"] == "REVIEWED" for row in corpus_authoring.build_corpus())
    profiles = copy.deepcopy(corpus_authoring.PROFILES)
    original = profiles["en"][0]
    profiles["en"][0] = ("I work as a database administrator.", "occupation", "database administrator", *original[3:])
    monkeypatch.setattr(corpus_authoring, "PROFILES", profiles)
    changed = corpus_authoring.build_corpus()
    assert all(row["independent_review"] == "PENDING" and "review_reference" not in row for row in changed)


@pytest.mark.parametrize(
    "scenario_id,field,value",
    [
        ("en-013", "education", "electrical engineering degree"),
        ("en-013", "education", "bachelor in electrical engineering"),
        ("en-013", "education", "electrical engineering"),
        ("en-002", "location", "Kazakhstan"),
        ("en-002", "location", "Astana region"),
        ("en-002", "location", "Астана"),
        ("en-001", "occupation", "senior backend engineer"),
        ("en-001", "tech_stack", "MySQL"),
        ("en-004", "communication_preferences", "brief"),
    ],
)
def test_aliases_do_not_admit_wrong_type_level_identity_or_protocol(corpus, scenario_id, field, value):
    scenario = next(row for row in corpus if row["scenario_id"] == scenario_id)
    checkpoint = scenario["checkpoints"][0]
    fact = next(row for row in checkpoint["facts"] if row["field"] == field)
    assert not inspect(scenario, checkpoint, {**fact, "value": value})


def test_alias_lookup_does_not_cross_source_language_or_unreviewed_text():
    text = "Я работаю бэкенд-разработчиком."
    assert accepted_values_for("ru", text, "occupation", "", "бэкенд-разработчик") == ["бэкенд-разработчиком"]
    assert not accepted_values_for("kk", text, "occupation", "", "бэкенд-разработчик")
    assert not accepted_values_for("ru", "Я не работаю бэкенд-разработчиком.", "occupation", "", "бэкенд-разработчик")


def test_complete_supporting_claim_may_omit_only_terminal_punctuation(corpus):
    observations = collect_observations(corpus, OracleSelfCheck())
    row = next(row for row in observations if row["scenario_id"] == "en-001")
    # These are complete verbatim claims without their final full stops.
    assert row["facts"][0]["evidence"]["end"] == len("I work as a backend engineer")
    assert row["facts"][1]["evidence"]["end"] == len("I use Python for my work")
    assert evaluate(corpus, observations)["numeric_thresholds_pass"]
    # Dropping the subject/predicate is not punctuation normalization.
    row["facts"][0]["evidence"]["start"] = len("I work as a ")
    assert not evaluate(corpus, observations)["numeric_thresholds_pass"]


def test_negative_claim_and_quoted_or_unsupported_sources_cannot_supply_facts(corpus):
    negative = next(row for row in corpus if row["scenario_id"] == "en-045")
    withdrawn = copy.deepcopy(negative["checkpoints"][0]["facts"][1])
    source = next(event for event in negative["events"] if event["event_id"] == "withdraw")
    withdrawn["evidence"] = {
        "source_event": "withdraw",
        "start": source["text"].index("Python"),
        "end": source["text"].index("Python") + len("Python"),
    }
    assert not inspect(negative, negative["checkpoints"][-1], withdrawn)
    quoted = next(row for row in corpus if row["scenario_id"] == "en-021")
    fact = copy.deepcopy(quoted["checkpoints"][-1]["facts"][0])
    for source_id in ("m4", "m2"):
        source = next(event for event in quoted["events"] if event["event_id"] == source_id)
        fact["evidence"] = {"source_event": source_id, "start": 0, "end": len(source["text"])}
        assert not inspect(quoted, quoted["checkpoints"][-1], fact)


def test_historical_edit_uses_original_time_before_activation_and_new_edit_time(corpus):
    cases = [row for row in corpus if "history_edit" in row["tags"]]
    assert len(cases) == 4
    for scenario in cases:
        event = scenario["events"][-1]
        assert event["type"] == "edit" and event["source_version"] == 2
        assert event["original_sent_at"] < scenario["learning_started_at"] < event["edited_at"]
        assert not any(
            fact["evidence"]["source_event"] == event["event_id"] for fact in scenario["checkpoints"][-1]["facts"]
        )


@pytest.mark.parametrize("language", ["kk", "ru", "en", "mixed"])
def test_actual_owner_rejects_pre_activation_edit_before_raw_or_model(corpus, language):
    scenario = next(row for row in corpus if row["scenario_id"] == language + "-056")
    adapter = DomainReplayAdapter(FixtureCatalog.read(FIXTURES / "provider_fixtures.jsonl"))
    observed = collect_observations([scenario], adapter)[-1]
    assert observed["replay"]["state"] == "EXECUTED"
    forbidden = scenario["events"][-1]["text"]
    surfaces = observed["traces"]["safety_surfaces"]
    assert all(forbidden not in text for surface in ("raw", "context") for text in surfaces[surface])
    assert not any(fact["evidence"]["source_event"] == "m4" for fact in observed["facts"])


def test_russian_education_questions_explicitly_ask_about_education(corpus):
    questions = [
        question
        for scenario in corpus
        for checkpoint in scenario["checkpoints"]
        for question in checkpoint["questions"]
    ]
    assert not any(question["text"] == "Какую специальность этот участник сам сообщил?" for question in questions)
    revised = [
        question for question in questions if question["text"] == "Что этот участник рассказывал о своём образовании?"
    ]
    assert revised and all(
        question["requested_fields"] == ["education"] and question["expected"] == "abstain" for question in revised
    )


def test_provider_fixtures_are_independently_regenerated_and_preserve_admin_value(corpus):
    inputs = [project_scenario(row) for row in corpus]
    assert "accepted_values" not in json.dumps(inputs)
    generated = author_fixture_rows(inputs)
    assert generated == read_jsonl(FIXTURES / "provider_fixtures.jsonl")
    confirmations = [row for row in generated if row["kind"] == "confirmation"]
    assert len(confirmations) == 3
    for row in confirmations:
        assert row["response"]["changes"][0]["value"] == row["input_text"].split(":", 1)[1].strip()
        assert row["response"]["changes"][0]["value"].endswith(".")


def test_actual_admin_command_stores_the_complete_rule_value(corpus):
    scenario = next(row for row in corpus if row["scenario_id"] == "en-049")
    adapter = DomainReplayAdapter(FixtureCatalog.read(FIXTURES / "provider_fixtures.jsonl"))
    observed = collect_observations([scenario], adapter)[-1]
    assert observed["replay"]["state"] == "EXECUTED"
    rule = next(fact for fact in observed["facts"] if fact["field"] == "rule")
    assert rule["subject_id"] == "group"
    assert rule["value"] == "include code as text."
    assert rule["evidence"]["source_event"] == "confirm"
