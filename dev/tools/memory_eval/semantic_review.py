"""Offline, occurrence-scoped education review; never edits execution or strict gold.

A reviewer supplies semantic judgments. This module validates their bindings and
accounting, not the truth of their natural-language judgment. No provider or AWS
client is imported; production readiness is always false.
"""

import argparse
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .__main__ import source_provenance
from .contract import (
    LANGUAGES,
    ZERO_GATES,
    EvaluationInputError,
    _invalid_constant,
    _object,
    fact_key,
    fingerprint,
    normalise,
    validate_corpus,
)
from .evaluator import _events_at, _inspect_assertion, _invalidated_sources, _summary, evaluate
from .replay_input import project_scenario

VERSION = "education-qualification-review-v1"
QUALIFICATION_CHECKS = (
    "subject",
    "credential_kind",
    "credential_level",
    "completion_or_temporal_status",
    "no_extra_claim",
)
REGISTRATION_KEYS = {
    "schema_version",
    "policy_sha256",
    "manifest_sha256",
    "corpus_file_sha256",
    "execution_source_sha256",
    "reviewer_ids",
    "implementation_author",
    "approved_at",
    "approval_reference",
}
LIMIT = 64 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise EvaluationInputError(reason)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _regular(path):
    path = Path(os.path.abspath(path))
    require(all(not part.is_symlink() for part in (path, *path.parents)), "Symbolic input paths are not allowed")
    require(stat.S_ISREG(path.stat().st_mode), "Input must be a regular file")
    return path


def _finite_float(value):
    result = float(value)
    require(math.isfinite(result), "Non-finite JSON number")
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_constant, parse_float=_finite_float)
    except ValueError:
        raise EvaluationInputError("Invalid strict JSON") from None


def _schema(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), "Unexpected " + label + " schema")


def policy():
    """Executable rules are themselves inside the frozen run source fingerprint."""
    directory = Path(__file__).parent
    return {
        "schema_version": 1,
        "version": VERSION,
        "scope": "education_qualification_occurrences_only",
        "thresholds": {
            "precision": 0.95,
            "recall": 0.90,
            "source_support": 1.0,
            "unknown_abstention": 0.95,
            "supported_answer_recall": 0.90,
        },
        "zero_tolerance": list(ZERO_GATES),
        "qualification_checks": list(QUALIFICATION_CHECKS),
        "rules": [
            "Same explicit source, identity, field, facet, temporal status and complete gold evidence range.",
            "Preserve subject, credential kind and level, completion and temporal status; add no personal claim.",
            "One actual occurrence per expected occurrence; extras and missing items stay in denominators.",
            "Review all education occurrences including strict matches, and every delivered answer in full.",
            "Full-text rejection always blocks pass; non-education and unknown metrics cannot improve.",
            "Profile alone contributes TP/FP/FN; answer matches only affect source support and known completeness.",
            "Preserve original strict report, all languages, unsupported cases and zero-tolerance failures.",
        ],
        "files": {
            name: _sha(_regular(directory / name).read_bytes())
            for name in ("semantic_review.py", "evaluator.py", "contract.py")
        },
        "human_semantics": "Independent reviewer attestation; file hashes do not prove semantic truth.",
        "runtime_source_revision_epoch": "NOT_RECORDED",
    }


class ReadSet:
    """Bound bytes once, reject links, and detect changes before returning."""

    def __init__(self):
        self.files = {}

    def bytes(self, path):
        path = _regular(path)
        require(path.stat().st_size <= LIMIT, "Input exceeds review file limit")
        raw = path.read_bytes()
        require(len(raw) <= LIMIT, "Input exceeds review file limit")
        digest = _sha(raw)
        require(path not in self.files or self.files[path] == digest, "Input changed during review")
        self.files[path] = digest
        return raw

    def json(self, path):
        return _json(self.bytes(path))

    def jsonl(self, path):
        rows = [_json(line) for line in self.bytes(path).splitlines() if line.strip()]
        require(all(isinstance(row, dict) for row in rows), "JSONL records must be objects")
        return rows

    def verify(self):
        for path, digest in list(self.files.items()):
            require(_sha(_regular(path).read_bytes()) == digest, "Input changed during review")


def _source(root):
    root = Path(root)
    for scope in ("src/bot", "src/shared/python", "dev/tools/memory_eval"):
        require((root / scope).is_dir(), "Missing execution source scope")
        require(
            all(not part.is_symlink() for part in ((root / scope), *(root / scope).parents)),
            "Execution source contains a symbolic scope",
        )
        for path in (root / scope).rglob("*"):
            require(not path.is_symlink(), "Execution source contains a symbolic path")
    for name in ("pyproject.toml", "uv.lock"):
        _regular(root / name)
    return source_provenance(root)


@dataclass(frozen=True)
class ReviewRun:
    corpus: list
    observations: list
    strict_report: dict
    bindings: dict


def _registration(reader, registration_path, run_dir, manifest, corpus_file_sha, current_policy, frozen_root):
    if registration_path is None:
        return {
            "mode": "RETROSPECTIVE_DIAGNOSTIC",
            "reviewer_ids": [],
            "implementation_author": None,
            "reason": "No pre-call registration supplied",
        }
    registration = reader.json(registration_path)
    _schema(registration, REGISTRATION_KEYS, "registration")
    require(registration["schema_version"] == 1, "Unknown registration version")
    for key, expected in {
        "policy_sha256": fingerprint(current_policy),
        "manifest_sha256": fingerprint(manifest),
        "corpus_file_sha256": corpus_file_sha,
        "execution_source_sha256": manifest["execution_source_sha256"],
    }.items():
        require(registration[key] == expected, "Registration binding mismatch")
    reviewers = registration["reviewer_ids"]
    require(
        isinstance(reviewers, list)
        and reviewers
        and all(isinstance(x, str) and x.strip() == x and x for x in reviewers),
        "Registration needs reviewer identities",
    )
    require(len(set(reviewers)) == len(reviewers), "Duplicate reviewer identity")
    author = registration["implementation_author"]
    require(
        isinstance(author, str) and author.strip() == author and author and author not in reviewers,
        "Reviewer must be independent of the implementation author",
    )
    require(
        isinstance(registration["approval_reference"], str) and registration["approval_reference"].strip(),
        "Registration needs an operator approval reference",
    )
    approved = registration["approved_at"]
    require(type(approved) in (int, float) and math.isfinite(approved) and approved > 0, "Invalid approval time")
    for name, digest in current_policy["files"].items():
        require(
            _sha(reader.bytes(frozen_root / "dev/tools/memory_eval" / name)) == digest,
            "Review policy was not included in the frozen execution source",
        )
    ledger = _regular(run_dir / "attempts.sqlite3")
    require(not any(Path(str(ledger) + suffix).exists() for suffix in ("-wal", "-journal")), "Ledger is not quiescent")
    reader.bytes(ledger)
    with sqlite3.connect(ledger.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        config = db.execute("SELECT id, fingerprint FROM config").fetchall()
        count, earliest = db.execute("SELECT COUNT(*), MIN(started_at) FROM attempts").fetchone()
    require(config == [(1, fingerprint(manifest))], "Ledger manifest binding mismatch")
    require(
        count > 0 and type(earliest) in (float, int) and math.isfinite(earliest) and approved < earliest,
        "Registration must precede the first recorded attempt",
    )
    return {
        "mode": "SOURCE_BOUND_OPERATOR_REGISTERED",
        "registration": registration,
        "registration_sha256": reader.files[_regular(registration_path)],
        "first_attempt_at": earliest,
        "reviewer_ids": reviewers,
        "implementation_author": author,
        "limitation": "Source binding plus operator approval attestation, not cryptographic chronology or semantics",
    }


def load_run(corpus_path, run_dir, execution_root, *, registration_path=None):
    """Read a finished public run under its existing shared lock, without creating files."""
    reader = ReadSet()
    run_dir, root = Path(run_dir).absolute(), Path(execution_root).absolute()
    lock = _regular(run_dir / "session.lock")
    with lock.open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EvaluationInputError("Evaluation is still running") from None
        corpus = reader.jsonl(corpus_path)
        info = validate_corpus(corpus)
        manifest = reader.json(run_dir / "session.json")
        state = reader.json(run_dir / "execution-status.json")
        provenance = reader.json(run_dir / "provenance.json")
        require(
            state == {"state": "FINISHED", "completed_scenarios": len(corpus), "planned_scenarios": len(corpus)},
            "Only complete finished runs can be reviewed",
        )
        require(manifest.get("answer_route") == provenance.get("answer_route") == "public-v1", "Public route required")
        require(provenance.get("provider_kind") == "recorded_provider", "Recorded provider provenance required")
        require(manifest["scenario_ids"] == [row["scenario_id"] for row in corpus], "Manifest scenario order changed")
        require(manifest["corpus_sha256"] == provenance["corpus_sha256"] == info["sha256"], "Corpus binding mismatch")
        projected = [project_scenario(row) for row in corpus]
        require(manifest["input_sha256"] == fingerprint(projected), "Projected input changed")
        source = _source(root)
        require(
            manifest["execution_source_sha256"]
            == provenance["execution_source_sha256"]
            == source["execution_source_sha256"],
            "Execution source fingerprint mismatch",
        )
        # Old execution roots are allowed only when their strict scorer is still the same implementation.
        for name in ("evaluator.py", "contract.py"):
            require(
                reader.bytes(root / "dev/tools/memory_eval" / name) == Path(__file__).with_name(name).read_bytes(),
                "Strict scorer/contract version changed",
            )
        observations = reader.jsonl(run_dir / "observations.jsonl")
        flattened, scene_hashes, executions = [], [], []
        paths = {p for p in (run_dir / "scenarios").iterdir()}
        expected_paths = {run_dir / "scenarios" / (fingerprint(s["scenario_id"]) + ".json") for s in corpus}
        require(paths == expected_paths, "Missing or unexpected scenario files")
        for scenario, expected_input in zip(corpus, projected):
            path = run_dir / "scenarios" / (fingerprint(scenario["scenario_id"]) + ".json")
            result = reader.json(path)
            _schema(result, {"scenario_id", "input_sha256", "status", "observations"}, "scenario result")
            require(
                result["scenario_id"] == scenario["scenario_id"]
                and result["input_sha256"] == fingerprint(expected_input),
                "Scenario input identity changed",
            )
            require(result["status"] in {"EXECUTED", "UNSUPPORTED"}, "Invalid scenario status")
            _replay_states(result["observations"])
            expected_status = (
                "UNSUPPORTED"
                if any(o["replay"]["state"] == "UNSUPPORTED" for o in result["observations"])
                else "EXECUTED"
            )
            require(result["status"] == expected_status, "Scenario and checkpoint replay states disagree")
            executions.append({k: result[k] for k in ("scenario_id", "input_sha256", "status")})
            require(
                [o["checkpoint_id"] for o in result["observations"]]
                == [c["checkpoint_id"] for c in scenario["checkpoints"]],
                "Scenario checkpoint coverage/order changed",
            )
            require(
                all(o["scenario_id"] == scenario["scenario_id"] for o in result["observations"]),
                "Wrong scenario observations",
            )
            flattened.extend(result["observations"])
            scene_hashes.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "file_sha256": reader.files[_regular(path)],
                    "projected_input_sha256": result["input_sha256"],
                }
            )
        require(flattened == observations, "Scenario files differ from aggregate observations")
        require(
            provenance.get("execution_status") == state
            and provenance.get("planned_scenarios") == len(corpus)
            and provenance.get("completed_scenarios") == len(corpus)
            and provenance.get("scenario_executions") == executions,
            "Provenance execution summaries disagree",
        )
        report = reader.json(run_dir / "report.json")
        require(
            evaluate(corpus, observations, provenance=provenance) == report, "Frozen strict report cannot be reproduced"
        )
        rules = policy()
        registration = _registration(
            reader, registration_path, run_dir, manifest, reader.files[_regular(corpus_path)], rules, root
        )
        bindings = {
            "policy_sha256": fingerprint(rules),
            "policy": rules,
            "registration": registration,
            "corpus_file_sha256": reader.files[_regular(corpus_path)],
            "corpus_json_sha256": fingerprint(corpus),
            "observations_json_sha256": fingerprint(observations),
            "strict_report_json_sha256": fingerprint(report),
            "execution_source_sha256": source["execution_source_sha256"],
            "scenario_files": scene_hashes,
            "files": {str(path): digest for path, digest in reader.files.items()},
            "runtime_source_revision_epoch": "NOT_RECORDED",
        }
        reader.verify()
        require(_source(root) == source and policy() == rules, "Executable source changed during review")
        return ReviewRun(corpus, observations, report, bindings)


def _replay_states(observations):
    require(isinstance(observations, list), "Observation list required")
    for observation in observations:
        require(isinstance(observation, dict), "Observation object required")
        replay = observation.get("replay")
        require(
            isinstance(replay, dict)
            and isinstance(replay.get("state"), str)
            and replay["state"] in {"EXECUTED", "UNSUPPORTED"},
            "Invalid or missing checkpoint replay state",
        )


def _index(corpus, observations):
    # Preserve the original scorer's validation, denominators and source of truth.
    _replay_states(observations)
    evaluate(corpus, observations)
    return {(o["scenario_id"], o["checkpoint_id"]): o for o in observations}


def _delivery_bindings(corpus, indexed):
    """Bijection between newly observed sends/routes and this checkpoint's answers."""
    result = {}
    for scenario in corpus:
        previous_sends, previous_routes, seen_messages = [], [], set()
        for cp in scenario["checkpoints"]:
            observation = indexed.get((scenario["scenario_id"], cp["checkpoint_id"]))
            if observation is None:
                continue
            traces = observation.get("traces", {})
            sends, routes = traces.get("sent_actions"), traces.get("public_route")
            require(isinstance(sends, list) and isinstance(routes, list), "Public delivery traces missing")
            require(
                sends[: len(previous_sends)] == previous_sends and routes[: len(previous_routes)] == previous_routes,
                "Cumulative delivery trace prefix changed",
            )
            new_sends, new_routes = sends[len(previous_sends) :], routes[len(previous_routes) :]
            require(all(isinstance(row, dict) for row in new_sends + new_routes), "Delivery trace object required")
            for row in new_sends:
                identity = (row.get("chat_id"), row.get("message_id"))
                require(
                    isinstance(identity[0], str) and type(identity[1]) is int and identity not in seen_messages,
                    "Send identity is invalid or reused across checkpoints",
                )
                seen_messages.add(identity)
            claimed_sends, claimed_routes = set(), set()
            answers = {a["question_id"]: a for a in observation["answers"]}
            for question in cp.get("questions", []):
                answer = answers.get(question["question_id"])
                route_indices = [
                    i for i, row in enumerate(new_routes) if row.get("question_id") == question["question_id"]
                ]
                if answer is None and not route_indices:
                    result[(scenario["scenario_id"], question["question_id"])] = None
                    continue
                require(
                    len(route_indices) == 1 and route_indices[0] not in claimed_routes,
                    "Missing or duplicated delivery route",
                )
                delivery = new_routes[route_indices[0]]
                _schema(
                    delivery, {"question_id", "request_id", "route", "state", "message_ids", "transport"}, "delivery"
                )
                mid = 1_000_000_000 + int(fingerprint(question["question_id"])[:12], 16) % 900_000_000
                require(
                    delivery.get("question_id") == question["question_id"]
                    and delivery.get("request_id") == f"tg:{question['chat_id']}:{mid}"
                    and delivery.get("route") in {"memory", "plain"}
                    and delivery.get("transport") == "synthetic_telegram_sink_with_real_persistence",
                    "Delivery identity changed",
                )
                if answer is None:
                    require(
                        delivery.get("state") in {"NOT_SENT", "READY", "UNKNOWN", "SENDING", "PARTIAL"}
                        and delivery.get("message_ids") == [],
                        "Missing answer cannot hide any delivery",
                    )
                    claimed_routes.add(route_indices[0])
                    result[(scenario["scenario_id"], question["question_id"])] = {
                        "delivery": delivery,
                        "sent_actions": [],
                        "response_text": [],
                    }
                    continue
                require(
                    delivery.get("state") == "SENT" and answer.get("delivery") == delivery,
                    "Answer lacks matching SENT receipt",
                )
                ids, texts = delivery.get("message_ids"), answer.get("response_text")
                require(
                    isinstance(ids, list) and ids and all(type(i) is int for i in ids) and len(ids) == len(set(ids)),
                    "Delivery message IDs must be nonempty and unique",
                )
                require(
                    isinstance(texts, list) and len(texts) == len(ids) and all(isinstance(t, str) for t in texts),
                    "Delivered text is missing",
                )
                route_indices = [
                    i for i, row in enumerate(new_routes) if row.get("question_id") == question["question_id"]
                ]
                require(
                    len(route_indices) == 1
                    and new_routes[route_indices[0]] == delivery
                    and route_indices[0] not in claimed_routes,
                    "Delivery route is absent, duplicated or reused",
                )
                claimed_routes.add(route_indices[0])
                selected = []
                for message_id, text in zip(ids, texts):
                    indices = [
                        i
                        for i, row in enumerate(new_sends)
                        if row.get("chat_id") == question["chat_id"] and row.get("message_id") == message_id
                    ]
                    require(
                        len(indices) == 1 and indices[0] not in claimed_sends, "Send is absent, duplicated or reused"
                    )
                    i = indices[0]
                    require(
                        new_sends[i]
                        == {
                            "kind": "explicit_answer",
                            "chat_id": question["chat_id"],
                            "message_id": message_id,
                            "text": text,
                        },
                        "SENT text or destination changed",
                    )
                    selected.append(i)
                    claimed_sends.add(i)
                require(selected == sorted(selected), "Delivered message order changed")
                result[(scenario["scenario_id"], question["question_id"])] = {
                    "delivery": delivery,
                    "sent_actions": [new_sends[i] for i in selected],
                    "response_text": texts,
                }
            require(
                claimed_sends == set(range(len(new_sends))) and claimed_routes == set(range(len(new_routes))),
                "Unreviewed orphan sends or routes exist",
            )
            previous_sends, previous_routes = sends, routes
    return result


def _entry(key, language, fact, sources, *, question=None, answer=None, delivery=None):
    source = sources.get((fact.get("evidence") or {}).get("source_event"))
    evidence = fact.get("evidence") or {}
    start, end = evidence.get("start"), evidence.get("end")
    valid = source and type(start) is int and type(end) is int and 0 <= start < end <= len(source["text"])
    row = {
        "id": fingerprint(key),
        "key": key,
        "language": language,
        "fact": fact,
        "source": source,
        "source_sha256": fingerprint(source),
        "span": {
            "start": start,
            "end": end,
            "excerpt_sha256": _sha(source["text"][start:end].encode()) if valid else None,
        },
        "question": question,
        "answer_sha256": fingerprint(answer),
        "delivery_sha256": fingerprint(delivery),
    }
    return {**row, "sha256": fingerprint(row)}


def build_inventory(corpus, observations, bindings):
    require(
        bindings["policy"] == policy() and bindings["policy_sha256"] == fingerprint(policy()), "Review policy changed"
    )
    require(
        bindings["corpus_json_sha256"] == fingerprint(corpus)
        and bindings["observations_json_sha256"] == fingerprint(observations),
        "Inventory input changed",
    )
    indexed = _index(corpus, observations)
    deliveries = _delivery_bindings(corpus, indexed)
    expected, actual, answers, denominators = [], [], [], {lang: Counter() for lang in LANGUAGES}
    for scenario in corpus:
        sid, language = scenario["scenario_id"], scenario["language"]
        counts = denominators[language]
        counts["scenarios"] += 1
        for cp in scenario["checkpoints"]:
            cid = cp["checkpoint_id"]
            counts["checkpoints"] += 1
            counts["gold_profile"] += len(cp["facts"])
            observation = indexed.get((sid, cid), {"facts": [], "answers": []})
            sources = {
                e["event_id"]: e
                for e in _events_at(scenario, cp)
                if e["type"] in {"message", "edit", "admin_confirmation"}
            }
            scopes = [("profile", None, cp["facts"], observation["facts"], None, None, None)]
            for question in cp.get("questions", []):
                qid = question["question_id"]
                answer = next((a for a in observation["answers"] if a["question_id"] == qid), None)
                delivery = deliveries.get((sid, qid))
                counts["known" if question["expected"] == "supported" else "unknown"] += 1
                row = {
                    "id": fingerprint([sid, cid, qid]),
                    "key": [sid, cid, qid],
                    "language": language,
                    "question": question,
                    "answer": answer,
                    "delivery": delivery,
                }
                answers.append({**row, "sha256": fingerprint(row)})
                expected_facts = [f for f in cp["facts"] if f["fact_id"] in question["supporting_fact_ids"]]
                scopes.append(
                    ("answer", qid, expected_facts, answer["assertions"] if answer else [], question, answer, delivery)
                )
            for surface, qid, gold_facts, facts, query, answer, delivery in scopes:
                for fact in gold_facts:
                    if fact["field"] == "education":
                        key = [sid, cid, surface, qid, fact["fact_id"]]
                        expected.append(
                            _entry(key, language, fact, sources, question=query, answer=answer, delivery=delivery)
                        )
                        counts["expected_education_" + surface] += 1
                for i, fact in enumerate(facts):
                    if fact.get("field") == "education":
                        key = [sid, cid, surface, qid, i]
                        actual.append(
                            _entry(key, language, fact, sources, question=query, answer=answer, delivery=delivery)
                        )
                        counts["actual_education_" + surface] += 1
    return {
        "schema_version": 1,
        "policy_sha256": bindings["policy_sha256"],
        "bindings": bindings,
        "denominators": {lang: dict(counts) for lang, counts in denominators.items()},
        "expected": expected,
        "actual": actual,
        "answers": answers,
        "review_status": "AWAITING_INDEPENDENT_TEXT_REVIEW",
    }


def _mechanical(actual, expected, scenario, checkpoint):
    """Value-independent education-only source gate; lifecycle truth remains in evaluator."""
    a, g = actual["fact"], expected["fact"]
    if a.get("field") != "education" or g.get("field") != "education":
        return False
    if fact_key(a)[:-1] != fact_key(g)[:-1] or a.get("temporal_status", "current") != g.get(
        "temporal_status", "current"
    ):
        return False
    evidence, gold = a.get("evidence") or {}, g["evidence"]
    events = _events_at(scenario, checkpoint)
    invalid = _invalidated_sources(events)
    source = actual["source"]
    if source is None or evidence.get("source_event") != gold["source_event"] or source["event_id"] in invalid:
        return False
    start, end = evidence.get("start"), evidence.get("end")
    if not (
        type(start) is int
        and type(end) is int
        and 0 <= start <= gold["start"] < gold["end"] <= end <= len(source["text"])
        and end - start <= 240
    ):
        return False
    return bool(
        source.get("safe") is True
        and not source.get("forwarded")
        and not source.get("is_bot")
        and source["chat_id"] == a["chat_id"]
        and source["user_id"] == a["subject_id"]
        and source["original_sent_at"] >= scenario["learning_started_at"]
        and not any(start < right and end > left for left, right in source.get("quoted_spans", []))
        and not any(normalise(marker) in normalise(a["value"]) for marker in scenario.get("sensitive_markers", []))
    )


def _decisions(inventory, decisions):
    require(isinstance(decisions, list), "Review decisions must be a list")
    inventory_digest = fingerprint(inventory)
    expected = {e["id"]: e for e in inventory["expected"]}
    actual = {e["id"]: e for e in inventory["actual"]}
    answers = {e["id"]: e for e in inventory["answers"]}
    registration = inventory["bindings"]["registration"]
    seen_expected, seen_actual, mappings, full_text = set(), set(), {}, {}
    unresolved, reviewers = [], set()
    common = {
        "schema_version",
        "kind",
        "policy_sha256",
        "inventory_sha256",
        "reviewer_id",
        "review_method",
        "verdict",
        "reason",
        "rationale",
    }
    for decision in decisions:
        require(isinstance(decision, dict), "Review decision object required")
        fields = (
            {"expected_id", "expected_sha256", "actual_id", "actual_sha256", "qualification_checks"}
            if decision.get("kind") == "education"
            else {"answer_id", "answer_sha256", "zero_tolerance_findings"}
        )
        _schema(decision, common | fields, "decision")
        require(
            decision["schema_version"] == 1 and decision["kind"] in {"education", "answer"},
            "Unknown decision kind/version",
        )
        require(
            decision["policy_sha256"] == inventory["policy_sha256"]
            and decision["inventory_sha256"] == inventory_digest,
            "Decision is bound to another policy or inventory",
        )
        reviewer = decision["reviewer_id"]
        require(
            isinstance(reviewer, str)
            and reviewer.strip() == reviewer
            and reviewer
            and reviewer != registration.get("implementation_author"),
            "Independent reviewer identity required",
        )
        if registration["mode"] == "SOURCE_BOUND_OPERATOR_REGISTERED":
            require(reviewer in registration["reviewer_ids"], "Reviewer is outside the registration")
        require(decision["review_method"] == "independent_text_review", "Model observations are not independent review")
        require(
            all(isinstance(decision[k], str) and decision[k].strip() for k in ("reason", "rationale")),
            "Review rationale missing",
        )
        reviewers.add(reviewer)
        verdict = decision["verdict"]
        require(isinstance(verdict, str), "Review verdict string required")
        if decision["kind"] == "answer":
            aid = decision["answer_id"]
            require(
                isinstance(aid, str)
                and aid in answers
                and aid not in full_text
                and decision["answer_sha256"] == answers[aid]["sha256"],
                "Duplicate or drifted answer review",
            )
            require(verdict in {"CONFIRMED", "UNSUPPORTED", "UNRESOLVED", "MISSING"}, "Invalid full-text verdict")
            require(
                (verdict == "MISSING") == (answers[aid]["answer"] is None), "Missing verdict must match actual absence"
            )
            findings = decision["zero_tolerance_findings"]
            require(
                isinstance(findings, list)
                and all(isinstance(f, str) for f in findings)
                and len(findings) == len(set(findings))
                and set(findings) <= set(ZERO_GATES),
                "Invalid manual zero-tolerance findings",
            )
            require(not findings or verdict == "UNSUPPORTED", "Findings require unsupported verdict")
            full_text[aid] = decision
        else:
            eid, aid = decision["expected_id"], decision["actual_id"]
            require(eid is not None or aid is not None, "Empty occurrence decision")
            for identity, rows, seen, digest in (
                (eid, expected, seen_expected, decision["expected_sha256"]),
                (aid, actual, seen_actual, decision["actual_sha256"]),
            ):
                require(
                    (identity is None and digest is None)
                    or (
                        isinstance(identity, str)
                        and identity in rows
                        and identity not in seen
                        and digest == rows[identity]["sha256"]
                    ),
                    "Occurrence missing, duplicated or changed",
                )
                if identity is not None:
                    seen.add(identity)
            checks = decision["qualification_checks"]
            _schema(checks, QUALIFICATION_CHECKS, "qualification checks")
            require(all(type(v) is bool for v in checks.values()), "Qualification checks must be booleans")
            if eid is None:
                require(verdict == "UNEXPECTED", "Unmatched actual must remain unexpected")
            elif aid is None:
                require(verdict == "MISSING", "Unmatched expected must remain missing")
            else:
                require(expected[eid]["key"][:4] == actual[aid]["key"][:4], "Cross-surface or cross-question matching")
                require(verdict in {"SUPPORTED", "UNSUPPORTED", "UNRESOLVED"}, "Invalid mapped verdict")
            require(verdict != "SUPPORTED" or all(checks.values()), "Supported qualification needs every check")
            if aid is not None:
                mappings[aid] = (eid, decision)
        if verdict == "UNRESOLVED":
            unresolved.append(
                {
                    "kind": decision["kind"],
                    "reason": decision["reason"],
                    "decision_sha256": fingerprint(decision),
                    "expected_id": decision.get("expected_id"),
                    "actual_id": decision.get("actual_id"),
                    "answer_id": decision.get("answer_id"),
                }
            )
    missing = {
        "expected": sorted(set(expected) - seen_expected),
        "actual": sorted(set(actual) - seen_actual),
        "answers": sorted(set(answers) - set(full_text)),
    }
    return expected, actual, mappings, full_text, missing, unresolved, sorted(reviewers)


def verify_review(corpus, observations, strict_report, inventory, decisions, *, bindings):
    require(build_inventory(corpus, observations, bindings) == inventory, "Inventory is stale or altered")
    strict = evaluate(corpus, observations, provenance=strict_report.get("provenance"))
    require(
        strict == strict_report and fingerprint(strict) == bindings["strict_report_json_sha256"],
        "Original strict report changed",
    )
    expected_rows, actual_rows, mappings, full_text, missing, unresolved, reviewers = _decisions(inventory, decisions)
    actual_by_key = {tuple(a["key"]): a for a in actual_rows.values()}
    indexed = _index(corpus, observations)
    counts_by_language = {lang: Counter() for lang in LANGUAGES}
    adjustments, mechanical_failures, manual_failures, manual_zero = [], [], [], Counter()
    for scenario in corpus:
        sid, counts = scenario["scenario_id"], counts_by_language[scenario["language"]]
        for cp in scenario["checkpoints"]:
            cid = cp["checkpoint_id"]
            obs = indexed.get((sid, cid))
            counts["gold_observations"] += len(cp["facts"])
            if obs is None:
                counts["fn"] += len(cp["facts"])
                counts["missing_checkpoints"] += 1
                counts["unknown_questions"] += sum(q["expected"] == "abstain" for q in cp.get("questions", []))
                counts["supported_questions"] += sum(q["expected"] == "supported" for q in cp.get("questions", []))
                continue
            events = _events_at(scenario, cp)
            sources = {
                e["event_id"]: {**e, "learning_started_at": scenario["learning_started_at"]}
                for e in events
                if e["type"] in {"message", "edit", "admin_confirmation"}
            }
            invalid = _invalidated_sources(events)

            def match(
                assertion, gold, key, query=None, *, sources=sources, invalid=invalid, scenario=scenario, checkpoint=cp
            ):
                strict_match, strict_support, _, _ = _inspect_assertion(
                    assertion, gold, sources, invalid, scenario.get("sensitive_markers", []), query=query
                )
                if assertion.get("field") != "education":
                    return strict_match, strict_support
                row = actual_by_key[tuple(key)]
                pair = mappings.get(row["id"])
                matched, supported = None, False
                if pair and pair[0] is not None and pair[1]["verdict"] == "SUPPORTED":
                    expected = expected_rows[pair[0]]
                    require(
                        expected["fact"]["fact_id"] in {g["fact_id"] for g in gold},
                        "Review used a fact outside this question",
                    )
                    if _mechanical(row, expected, scenario, checkpoint):
                        matched, supported = expected["fact"], True
                    else:
                        mechanical_failures.append(row["id"])
                strict_id = strict_match["fact_id"] if strict_match else None
                semantic_id = matched["fact_id"] if matched else None
                if strict_id != semantic_id or strict_support != supported:
                    adjustments.append(
                        {
                            "actual_id": row["id"],
                            "expected_id": pair[0] if pair else None,
                            "surface": key[2],
                            "strict_fact_id": strict_id,
                            "semantic_fact_id": semantic_id,
                            "strict_source_supported": strict_support,
                            "semantic_source_supported": supported,
                            "decision_sha256": fingerprint(pair[1]) if pair else None,
                            "reviewer_id": pair[1]["reviewer_id"] if pair else None,
                        }
                    )
                return matched, supported

            seen = set()
            for i, assertion in enumerate(obs["facts"]):
                matched, supported = match(assertion, cp["facts"], [sid, cid, "profile", None, i])
                counts["assertions"] += 1
                counts["supported_assertions"] += int(supported)
                if matched and matched["fact_id"] not in seen:
                    counts["tp"] += 1
                    seen.add(matched["fact_id"])
                else:
                    counts["fp"] += 1
            counts["fn"] += len(cp["facts"]) - len(seen)
            by_question = {a["question_id"]: a for a in obs["answers"]}
            for query in cp.get("questions", []):
                qid = query["question_id"]
                answer = by_question.get(qid)
                counts["missing_answers"] += int(answer is None)
                aid = fingerprint([sid, cid, qid])
                review = full_text.get(aid)
                confirmed = review is not None and review["verdict"] == "CONFIRMED"
                if review and review["verdict"] == "UNSUPPORTED":
                    manual_failures.append(aid)
                    manual_zero.update(review["zero_tolerance_findings"])
                if query["expected"] == "abstain":
                    counts["unknown_questions"] += 1
                    counts["unknown_abstained"] += int(
                        bool(confirmed and answer and answer["abstained"] and not answer["assertions"])
                    )
                supported_ids = set()
                gold = [g for g in cp["facts"] if g["fact_id"] in query["supporting_fact_ids"]]
                for i, assertion in enumerate(answer["assertions"] if answer else []):
                    matched, supported = match(assertion, gold, [sid, cid, "answer", qid, i], query=query)
                    counts["assertions"] += 1
                    counts["supported_assertions"] += int(supported)
                    if supported:
                        supported_ids.add(matched["fact_id"])
                if query["expected"] == "supported":
                    counts["supported_questions"] += 1
                    counts["supported_answers_complete"] += int(
                        bool(
                            confirmed
                            and answer
                            and not answer["abstained"]
                            and supported_ids == set(query["supporting_fact_ids"])
                        )
                    )
    complete = not any(missing.values()) and not unresolved and strict["complete"]
    languages = {lang: _summary(counts) for lang, counts in counts_by_language.items()}
    total = Counter()
    for counts in counts_by_language.values():
        total.update(counts)
    numeric = complete and strict["corpus"]["size_gate"] and all(c["thresholds_pass"] for c in languages.values())
    gates = all(g["status"] == "PASS" for g in strict["zero_tolerance"].values()) and not any(manual_zero.values())
    passed = bool(numeric and gates and not manual_failures and not mechanical_failures)
    status = "INCOMPLETE" if not complete else "PASS_SEMANTIC_MEASUREMENT" if passed else "FAIL"
    if bindings["registration"]["mode"] == "RETROSPECTIVE_DIAGNOSTIC":
        status = "RETROSPECTIVE_DIAGNOSTIC"
    completeness = {}
    for language in LANGUAGES:
        language_missing = {
            kind: sum(row["language"] == language and row["id"] in missing[kind] for row in inventory[kind])
            for kind in ("expected", "actual", "answers")
        }
        unresolved_ids = {
            r[k] for r in unresolved for k in ("expected_id", "actual_id", "answer_id") if r[k] is not None
        }
        unresolved_count = sum(
            row["language"] == language and row["id"] in unresolved_ids
            for kind in ("expected", "actual", "answers")
            for row in inventory[kind]
        )
        completeness[language] = {
            "missing": language_missing,
            "unresolved_occurrences": unresolved_count,
            "complete": not any(language_missing.values()) and unresolved_count == 0,
        }
    return {
        "schema_version": 1,
        "policy_sha256": inventory["policy_sha256"],
        "inventory_sha256": fingerprint(inventory),
        "decisions_sha256": fingerprint(decisions),
        "review_completeness_by_language": completeness,
        "strict_report_sha256": fingerprint(strict),
        "strict_metrics_unchanged": strict["languages"],
        "status": status,
        "complete": complete,
        "semantic_numeric_thresholds_pass": bool(numeric),
        "semantic_review_gates_pass": passed,
        "languages": languages,
        "overall": _summary(total),
        "adjustments_by_occurrence": adjustments,
        "mechanical_failures": mechanical_failures,
        "missing_reviews": missing,
        "unresolved_reviews": unresolved,
        "reviewers": reviewers,
        "manual_unsupported_answers": manual_failures,
        "manual_zero_tolerance_findings": dict(manual_zero),
        "inherited_zero_tolerance": strict["zero_tolerance"],
        "inherited_runtime_replay": strict["runtime_replay"],
        "inherited_coverage": strict["coverage"],
        "registration": bindings["registration"],
        "source_support_scope": "Observed assertions; independent complete-answer gate also required",
        "budget_pause_no_memory_forwarding": "NOT_VERIFIED_BY_THIS_TOOL",
        "runtime_source_revision_epoch": "NOT_RECORDED",
        "production_ready": False,
        "original_run_quality_status_unchanged": True,
    }


def _write_output(directory, files, inputs):
    target = Path(directory).absolute()
    for source in inputs:
        source = Path(source).resolve()
        require(
            target.resolve() != source and source not in target.resolve().parents,
            "Review output must be outside every input directory",
        )
    require(all(not part.is_symlink() for part in (target, *target.parents)), "Symbolic output path is not allowed")
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    for name, document in files.items():
        with (target / name).open("x") as stream:
            os.chmod(stream.name, 0o600)
            json.dump(document, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("policy", "inventory", "verify"))
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--execution-root", type=Path)
    parser.add_argument("--registration", type=Path)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "policy":
        _write_output(args.output, {"policy.json": policy()}, [Path(__file__).resolve().parents[3]])
        return 0
    require(all((args.corpus, args.run_dir, args.execution_root)), "Corpus, run and execution root are required")
    run = load_run(args.corpus, args.run_dir, args.execution_root, registration_path=args.registration)
    inventory = build_inventory(run.corpus, run.observations, run.bindings)
    inputs = [args.run_dir, args.execution_root, args.corpus.parent]
    if args.command == "inventory":
        files = {"inventory.json": inventory}
        status = "AWAITING_INDEPENDENT_TEXT_REVIEW"
    else:
        require(args.inventory and args.decisions, "Inventory and decisions are required")
        reader = ReadSet()
        require(reader.json(args.inventory) == inventory, "Provided inventory does not match current frozen input")
        decisions = reader.jsonl(args.decisions)
        report = verify_review(
            run.corpus, run.observations, run.strict_report, inventory, decisions, bindings=run.bindings
        )
        reader.verify()
        report["review_input_files"] = {str(path): digest for path, digest in reader.files.items()}
        files, status = {"report.json": report}, report["status"]
        inputs.extend([args.inventory.parent, args.decisions.parent])
    if args.registration:
        inputs.append(args.registration.parent)
    for path, digest in run.bindings["files"].items():
        require(_sha(_regular(path).read_bytes()) == digest, "Input changed before output")
    require(
        _source(args.execution_root)["execution_source_sha256"] == run.bindings["execution_source_sha256"]
        and policy() == run.bindings["policy"],
        "Source changed before output",
    )
    _write_output(args.output, files, inputs)
    print(json.dumps({"status": status, "output": str(args.output.absolute()), "production_ready": False}))
    return 0 if args.command == "inventory" or status == "PASS_SEMANTIC_MEASUREMENT" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EvaluationInputError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"status": "REVIEW_INPUT_REJECTED", "error_type": type(exc).__name__}))
        raise SystemExit(2) from None
