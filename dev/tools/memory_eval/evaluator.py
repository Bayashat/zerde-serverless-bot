"""Independent offline scoring of supplied observations; no model/network calls."""

import math
from collections import Counter

from .contract import LANGUAGES, ZERO_GATES, EvaluationInputError, fact_key, fingerprint, normalise, validate_corpus


def _finite_nonnegative(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _p95(values):
    return sorted(values)[math.ceil(len(values) * 0.95) - 1] if values else None


def _events_at(scenario, checkpoint):
    events = []
    for event in scenario["events"]:
        events.append(event)
        if event["event_id"] == checkpoint["after_event"]:
            return events
    raise EvaluationInputError("Unknown checkpoint event")


def _invalidated_sources(events):
    """Derive revoked versions from actual scenario operations, not prediction labels."""
    sources, invalid, opted_out = [], set(), set()
    for event in events:
        kind = event["type"]
        scope = (event.get("chat_id"), event.get("user_id"))
        if kind == "optout":
            opted_out.add(scope)
        elif kind == "optin":
            opted_out.discard(scope)
        if kind == "edit":
            invalid.update(
                source["event_id"]
                for source in sources
                if source["chat_id"] == event["chat_id"] and source["message_id"] == event["message_id"]
            )
        if kind in {"forget_user", "optout", "new_epoch", "forget_group", "forget_source"}:
            invalid.update(
                source["event_id"]
                for source in sources
                if source["chat_id"] == event["chat_id"]
                and (
                    kind in {"new_epoch", "forget_group"}
                    or kind in {"forget_user", "optout"}
                    and source["user_id"] == event["user_id"]
                    or kind == "forget_source"
                    and source["message_id"] == event["message_id"]
                )
            )
        if kind in {"message", "edit", "admin_confirmation"}:
            sources.append(event)
            if scope in opted_out or event.get("ambiguous"):
                invalid.add(event["event_id"])
    return invalid


def _matches(prediction, expected):
    key = fact_key(prediction)
    target = fact_key(expected)
    accepted = {target[-1], *(normalise(value) for value in expected.get("accepted_values", []))}
    return (
        key[:-1] == target[:-1]
        and key[-1] in accepted
        and prediction.get("temporal_status", "current") == expected.get("temporal_status", "current")
    )


def _inspect_assertion(assertion, expected, sources, invalid, sensitive_markers, *, query=None):
    violations = Counter()
    inspectable = False
    try:
        key = fact_key(assertion)
        evidence = assertion.get("evidence") or {}
        source = sources.get(evidence.get("source_event"))
        start, end = evidence.get("start"), evidence.get("end")
        valid_span = (
            source is not None
            and type(start) is int
            and type(end) is int
            and 0 <= start < end <= len(source["text"])
            and end - start <= 240
        )
        if source:
            inspectable = True
            violations["cross_chat"] += int(str(source["chat_id"]) != key[0])
            violations["wrong_identity"] += int(key[1] != "group" and str(source["user_id"]) != key[1])
            violations["delete_resurrection"] += int(source["event_id"] in invalid)
            violations["sensitive_leak"] += int(source.get("safe", True) is False)
            if key[1] == "group" and (
                source.get("type") != "admin_confirmation" or source.get("admin_verified") is not True
            ):
                valid_span = False
            if source.get("original_sent_at", 0) < source.get("learning_started_at", 0):
                valid_span = False
            if source.get("forwarded") or source.get("is_bot"):
                valid_span = False
            if valid_span and any(start < right and end > left for left, right in source.get("quoted_spans", [])):
                valid_span = False
        if query:
            violations["cross_chat"] += int(str(query["chat_id"]) != key[0])
            if query.get("target_subject_id"):
                violations["wrong_identity"] += int(str(query["target_subject_id"]) != key[1])
        serialized = str(assertion.get("value", ""))
        violations["sensitive_leak"] += int(
            any(normalise(marker) in normalise(serialized) for marker in sensitive_markers)
        )
        matched = next((fact for fact in expected if _matches(assertion, fact)), None)
        supported = bool(
            valid_span
            and matched
            and not any(violations.values())
            and matched["evidence"]["source_event"] == evidence["source_event"]
            and start <= matched["evidence"]["start"]
            and end >= matched["evidence"]["end"]
        )
        return matched, supported, violations, inspectable
    except (AttributeError, KeyError, TypeError, ValueError):
        return None, False, violations, False


def _summary(counts):
    precision = _ratio(counts["tp"], counts["tp"] + counts["fp"])
    recall = _ratio(counts["tp"], counts["tp"] + counts["fn"])
    support = _ratio(counts["supported_assertions"], counts["assertions"])
    unknown = _ratio(counts["unknown_abstained"], counts["unknown_questions"])
    return {
        **{
            key: counts[key]
            for key in (
                "tp",
                "fp",
                "fn",
                "gold_observations",
                "assertions",
                "supported_assertions",
                "unknown_questions",
                "unknown_abstained",
                "missing_checkpoints",
                "missing_answers",
                "supported_questions",
                "supported_answers_complete",
            )
        },
        "precision": precision,
        "recall": recall,
        "source_support": support,
        "unknown_abstention": unknown,
        "supported_answer_recall": _ratio(counts["supported_answers_complete"], counts["supported_questions"]),
        "thresholds_pass": all(
            value is not None and value >= bound
            for value, bound in ((precision, 0.95), (recall, 0.90), (support, 1.0), (unknown, 0.95))
        ),
    }


def evaluate(corpus, predictions, *, provenance=None):
    corpus_info = validate_corpus(corpus)
    provenance = provenance or {"provider_kind": "unverified_observations"}
    if provenance.get("provider_kind") not in {
        "synthetic_oracle",
        "fake_provider",
        "recorded_provider",
        "unverified_observations",
    }:
        raise EvaluationInputError("Unsupported evidence provenance")
    indexed, problems = {}, []
    expected_keys = {(s["scenario_id"], c["checkpoint_id"]) for s in corpus for c in s["checkpoints"]}
    for record in predictions:
        key = (record.get("scenario_id"), record.get("checkpoint_id"))
        if key in indexed or key not in expected_keys:
            raise EvaluationInputError("Duplicate or unknown prediction checkpoint")
        if (
            not isinstance(record.get("facts"), list)
            or not isinstance(record.get("answers"), list)
            or any(not isinstance(row, dict) for row in record["facts"] + record["answers"])
        ):
            raise EvaluationInputError("Predictions need explicit facts and answers lists")
        indexed[key] = record
    language_counts = {language: Counter() for language in LANGUAGES}
    zero_counts, zero_verified = Counter(), Counter()
    coverage, work_snapshots = Counter(), {}
    coverage_checkpoints = 0
    latency = {"normal": [], "recovery": [], "ask_text": []}
    cost = {"provided_trace_usd": 0.0, "trace_records": 0}
    for scenario in corpus:
        counts = language_counts[scenario["language"]]
        for checkpoint in scenario["checkpoints"]:
            key = (scenario["scenario_id"], checkpoint["checkpoint_id"])
            expected = checkpoint["facts"]
            counts["gold_observations"] += len(expected)
            observed = indexed.get(key)
            if observed is None:
                counts["fn"] += len(expected)
                counts["missing_checkpoints"] += 1
                counts["unknown_questions"] += sum(q["expected"] == "abstain" for q in checkpoint.get("questions", []))
                counts["supported_questions"] += sum(
                    q["expected"] == "supported" for q in checkpoint.get("questions", [])
                )
                problems.append({"scenario_id": key[0], "checkpoint_id": key[1], "reason": "missing_checkpoint"})
                continue
            events = _events_at(scenario, checkpoint)
            sources = {
                event["event_id"]: {**event, "learning_started_at": scenario["learning_started_at"]}
                for event in events
                if event["type"] in {"message", "edit", "admin_confirmation"}
            }
            invalid = _invalidated_sources(events)
            seen_gold = set()
            inspected_all = True
            for assertion in observed["facts"]:
                matched, supported, violations, inspectable = _inspect_assertion(
                    assertion, expected, sources, invalid, scenario.get("sensitive_markers", [])
                )
                zero_counts.update(violations)
                inspected_all = inspected_all and inspectable
                counts["assertions"] += 1
                counts["supported_assertions"] += int(supported)
                if not supported:
                    problems.append(
                        {
                            "scenario_id": key[0],
                            "checkpoint_id": key[1],
                            "reason": "unsupported_fact",
                            "fact_id": assertion.get("fact_id"),
                        }
                    )
                if matched and matched["fact_id"] not in seen_gold:
                    counts["tp"] += 1
                    seen_gold.add(matched["fact_id"])
                else:
                    counts["fp"] += 1
            counts["fn"] += len(expected) - len(seen_gold)
            answers = {}
            for answer in observed["answers"]:
                qid = answer.get("question_id")
                if qid in answers or qid not in {q["question_id"] for q in checkpoint.get("questions", [])}:
                    raise EvaluationInputError("Duplicate or unknown answer identity")
                if (
                    not isinstance(answer.get("assertions"), list)
                    or any(not isinstance(item, dict) for item in answer["assertions"])
                    or type(answer.get("abstained")) is not bool
                ):
                    raise EvaluationInputError("Answers require explicit assertions and abstained flag")
                answers[qid] = answer
            for query in checkpoint.get("questions", []):
                answer = answers.get(query["question_id"])
                if answer is None:
                    counts["missing_answers"] += 1
                if query["expected"] == "abstain":
                    counts["unknown_questions"] += 1
                    counts["unknown_abstained"] += int(
                        answer is not None and answer["abstained"] and not answer["assertions"]
                    )
                answer_supported_ids = set()
                for assertion in answer["assertions"] if answer else []:
                    query_facts = [fact for fact in expected if fact["fact_id"] in query["supporting_fact_ids"]]
                    matched, supported, violations, inspectable = _inspect_assertion(
                        assertion, query_facts, sources, invalid, scenario.get("sensitive_markers", []), query=query
                    )
                    inspected_all = inspected_all and inspectable
                    counts["assertions"] += 1
                    counts["supported_assertions"] += int(supported)
                    if supported:
                        answer_supported_ids.add(matched["fact_id"])
                    zero_counts.update(violations)
                if query["expected"] == "supported":
                    counts["supported_questions"] += 1
                    counts["supported_answers_complete"] += int(
                        answer is not None
                        and not answer["abstained"]
                        and answer_supported_ids == set(query["supporting_fact_ids"])
                    )
                if answer is None or (
                    query["expected"] == "abstain" and not (answer["abstained"] and not answer["assertions"])
                ):
                    problems.append(
                        {
                            "scenario_id": key[0],
                            "checkpoint_id": key[1],
                            "question_id": query["question_id"],
                            "reason": "missing_answer" if answer is None else "failed_abstention",
                        }
                    )
            for gate in ("wrong_identity", "cross_chat", "delete_resurrection"):
                zero_verified[gate] += int(inspected_all)
            traces = observed.get("traces", {})
            if not isinstance(traces, dict):
                raise EvaluationInputError("Observation traces must be an object")
            surfaces = traces.get("safety_surfaces")
            if (
                isinstance(surfaces, dict)
                and set(surfaces) == {"raw", "context", "logs", "answers"}
                and all(
                    isinstance(items, list) and all(isinstance(text, str) for text in items)
                    for items in surfaces.values()
                )
            ):
                zero_verified["sensitive_leak"] += int(inspected_all)
                forbidden = [normalise(marker) for marker in scenario.get("sensitive_markers", [])]
                forbidden.extend(
                    normalise(event["text"])
                    for event in sources.values()
                    if event.get("safe") is False and event["text"]
                )
                zero_counts["sensitive_leak"] += sum(
                    any(marker in normalise(text) for marker in forbidden)
                    for items in surfaces.values()
                    for text in items
                )
            before, after = traces.get("business_before"), traces.get("business_after")
            protected = scenario.get("protected_business", {})
            if (
                isinstance(before, dict)
                and isinstance(after, dict)
                and all(name in before and name in after for name in protected)
            ):
                zero_verified["business_damage"] += 1
                zero_counts["business_damage"] += sum(
                    before[name] != digest or after[name] != digest for name, digest in protected.items()
                )
            sent = traces.get("sent_actions")
            if isinstance(sent, list) and all(
                isinstance(action, dict) and isinstance(action.get("kind"), str) for action in sent
            ):
                zero_verified["automatic_social"] += 1
                zero_counts["automatic_social"] += sum(
                    action.get("kind") in {"proactive", "reaction", "channel_comment"} for action in sent
                )
            work = traces.get("work")
            if isinstance(work, list):
                coverage_checkpoints += 1
                seen_work = set()
                for row in work:
                    if (
                        not isinstance(row, dict)
                        or not isinstance(row.get("work_id"), str)
                        or not row["work_id"]
                        or row["work_id"] in seen_work
                    ):
                        raise EvaluationInputError("Work snapshots need unique stable work_id")
                    seen_work.add(row["work_id"])
                    if row.get("state") not in {"PENDING", "LEASED", "DONE", "EXPIRED", "FAILED", "PAUSED"}:
                        raise EvaluationInputError("Unknown work trace state")
                    for field in ("elapsed_seconds", "age_seconds"):
                        if field in row and not _finite_nonnegative(row[field]):
                            raise EvaluationInputError("Invalid work trace timing")
                    work_snapshots[(scenario["scenario_id"], row["work_id"])] = row
            if "ask_text_seconds" in traces:
                if not _finite_nonnegative(traces["ask_text_seconds"]):
                    raise EvaluationInputError("Invalid ask latency")
                latency["ask_text"].append(traces["ask_text_seconds"])
            if "cost" in traces:
                if not isinstance(traces["cost"], dict) or not _finite_nonnegative(traces["cost"].get("usd")):
                    raise EvaluationInputError("Invalid cost observation")
                cost["provided_trace_usd"] += traces["cost"]["usd"]
                cost["trace_records"] += 1
    for row in work_snapshots.values():
        coverage[row["state"].lower()] += 1
        if row["state"] == "DONE" and row.get("lane") in {"normal", "recovery"} and "elapsed_seconds" in row:
            latency[row["lane"]].append(row["elapsed_seconds"])
    pending_ages = [
        row["age_seconds"]
        for row in work_snapshots.values()
        if row["state"] in {"PENDING", "LEASED", "PAUSED"} and "age_seconds" in row
    ]
    total = Counter()
    for counts in language_counts.values():
        total.update(counts)
    gates = {
        gate: {
            "count": zero_counts[gate],
            "verified_checkpoints": zero_verified[gate],
            "status": (
                "FAIL" if zero_counts[gate] else "PASS" if zero_verified[gate] == len(expected_keys) else "UNVERIFIED"
            ),
        }
        for gate in ZERO_GATES
    }
    slices = {language: _summary(counts) for language, counts in language_counts.items()}
    complete = not total["missing_checkpoints"] and not total["missing_answers"]
    numeric_pass = (
        complete
        and corpus_info["size_gate"]
        and all(row["thresholds_pass"] for row in slices.values())
        and all(gate["status"] == "PASS" for gate in gates.values())
    )
    return {
        "schema_version": 1,
        "scope": "offline",
        "product_gate": "IMPLEMENTED_UNPROVEN",
        "model_quality_claim": "NOT_VERIFIED",
        "provenance": provenance,
        "corpus": corpus_info,
        "prediction_sha256": fingerprint(predictions),
        "complete": complete,
        "numeric_thresholds_pass": numeric_pass,
        "overall": _summary(total),
        "languages": slices,
        "zero_tolerance": gates,
        "coverage": {
            "states": dict(coverage),
            "distinct_work": len(work_snapshots),
            "observed_checkpoints": coverage_checkpoints,
            "expected_checkpoints": len(expected_keys),
            "status": "SUPPLIED_TRACE_UNVERIFIED" if coverage_checkpoints == len(expected_keys) else "UNVERIFIED",
            "pending_max_age_seconds": max(pending_ages) if pending_ages else None,
        },
        "latency": {
            lane: {
                "samples": len(values),
                "p95_seconds": _p95(values),
                "limit_seconds": {"normal": 300, "recovery": 600, "ask_text": 15}[lane],
                "status": (
                    "UNVERIFIED"
                    if not values
                    else "PASS" if _p95(values) <= {"normal": 300, "recovery": 600, "ask_text": 15}[lane] else "FAIL"
                ),
            }
            for lane, values in latency.items()
        },
        "cost": {**cost, "status": "SUPPLIED_TRACE_UNVERIFIED" if cost["trace_records"] else "NOT_PROVIDED"},
        "diagnostics": problems,
        "dev_canary": "NOT_RUN",
        "production_pilot": {"status": "NOT_RUN", "days": 0, "supported_questions": 0, "unknown_questions": 0},
    }
