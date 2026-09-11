"""Strict, human-readable corpus and observation contracts; no runtime imports."""

import hashlib
import json
import unicodedata
from pathlib import Path

LANGUAGES = ("kk", "ru", "en", "mixed")
SOURCE_TYPES = {"message", "edit", "admin_confirmation"}
ZERO_GATES = (
    "wrong_identity",
    "cross_chat",
    "sensitive_leak",
    "delete_resurrection",
    "business_damage",
    "automatic_social",
)
PERSONAL_FIELDS = {
    "occupation",
    "current_project",
    "location",
    "education",
    "tech_stack",
    "interests",
    "communication_preferences",
}
PROTECTED_KEYS = {"SETTINGS", "CHAT_STATS", "CAPTCHA_PENDING"}


class EvaluationInputError(ValueError):
    pass


def normalise(value):
    if not isinstance(value, str):
        raise EvaluationInputError("Fact values must be strings")
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationInputError("Duplicate JSON property")
        result[key] = value
    return result


def _invalid_constant(value):
    raise EvaluationInputError(f"Non-finite JSON number: {value}")


def read_jsonl(path):
    records = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line, object_pairs_hook=_object, parse_constant=_invalid_constant)
        except ValueError as exc:
            raise EvaluationInputError(f"Invalid JSONL line {number}") from exc
        if not isinstance(record, dict):
            raise EvaluationInputError(f"Line {number} is not an object")
        records.append(record)
    return records


def fingerprint(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def fact_key(fact):
    if not isinstance(fact, dict) or any(
        not isinstance(fact.get(key), str) or not fact[key] for key in ("chat_id", "subject_id", "field", "value")
    ):
        raise EvaluationInputError("Fact identity, field and value must be nonempty strings")
    if not isinstance(fact.get("facet", ""), str):
        raise EvaluationInputError("Fact facet must be a string")
    return tuple(fact[field] for field in ("chat_id", "subject_id", "field")) + (
        fact.get("facet", ""),
        normalise(fact["value"]),
    )


def _check_gold(fact, sources, available, sid):
    fact_key(fact)
    if fact["field"] not in PERSONAL_FIELDS | {"rule", "decision"} or not isinstance(fact.get("fact_id"), str):
        raise EvaluationInputError(f"Invalid gold field/id: {sid}")
    evidence = fact.get("evidence", {})
    source = sources.get(evidence.get("source_event"))
    start, end = evidence.get("start"), evidence.get("end")
    if (
        source is None
        or source["event_id"] not in available
        or type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(source["text"])
        or end - start > 240
    ):
        raise EvaluationInputError(f"Invalid or future gold evidence span: {sid}")
    if (
        source.get("safe") is not True
        or source.get("forwarded")
        or source.get("is_bot")
        or any(start < right and end > left for left, right in source.get("quoted_spans", []))
    ):
        raise EvaluationInputError(f"Ineligible gold source: {sid}")
    if source["chat_id"] != fact["chat_id"]:
        raise EvaluationInputError(f"Cross-chat gold evidence: {sid}")
    if fact["subject_id"] == "group":
        if (
            source["type"] != "admin_confirmation"
            or source.get("admin_verified") is not True
            or fact["field"] not in {"rule", "decision"}
        ):
            raise EvaluationInputError(f"Unconfirmed group gold fact: {sid}")
    elif source["user_id"] != fact["subject_id"] or fact["field"] not in PERSONAL_FIELDS:
        raise EvaluationInputError(f"Wrong gold author: {sid}")
    for value in fact.get("accepted_values", []):
        normalise(value)


def validate_corpus(corpus):
    ids, messages, questions, gold, review = set(), set(), set(), {}, set()
    counts = {lang: {"scenarios": 0, "gold_facts": 0, "unknown_questions": 0} for lang in LANGUAGES}
    for scenario in corpus:
        sid = scenario.get("scenario_id")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise EvaluationInputError("Missing or duplicate scenario identity")
        ids.add(sid)
        language = scenario.get("language")
        if (
            scenario.get("schema_version") != 1
            or language not in LANGUAGES
            or scenario.get("synthetic") is not True
            or scenario.get("authorship") != "ai_authored"
        ):
            raise EvaluationInputError(f"Unsupported corpus metadata: {sid}")
        review_status = scenario.get("independent_review")
        if review_status not in {"PENDING", "REVIEWED"}:
            raise EvaluationInputError(f"Missing label review status: {sid}")
        if review_status == "REVIEWED" and not scenario.get("review_reference"):
            raise EvaluationInputError(f"Reviewed labels need an evidence reference: {sid}")
        review.add(review_status)
        protected = scenario.get("protected_business")
        if (
            not isinstance(protected, dict)
            or set(protected) != PROTECTED_KEYS
            or any(not isinstance(value, str) or not value for value in protected.values())
        ):
            raise EvaluationInputError(f"Missing protected business snapshots: {sid}")
        events = scenario.get("events")
        if not isinstance(events, list) or len(events) < 3 or any(not isinstance(e, dict) for e in events):
            raise EvaluationInputError(f"Scenario must be substantively multi-turn: {sid}")
        event_ids = [event["event_id"] for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise EvaluationInputError(f"Duplicate source event: {sid}")
        sources = {event["event_id"]: event for event in events if event["type"] in SOURCE_TYPES}
        if len(sources) < 3:
            raise EvaluationInputError(f"Scenario needs at least three source turns: {sid}")
        for source in sources.values():
            if (
                any(
                    not isinstance(source.get(key), str)
                    for key in ("chat_id", "user_id", "message_id", "text", "epoch")
                )
                or type(source.get("source_version")) is not int
                or source["source_version"] < 1
            ):
                raise EvaluationInputError(f"Invalid source identity/version: {sid}")
            if type(source.get("original_sent_at")) is not int or type(source.get("edited_at")) is not int:
                raise EvaluationInputError(f"Source original and edit times required: {sid}")
        messages.add(tuple((event["type"], event.get("text", "")) for event in events))
        counts[language]["scenarios"] += 1
        checkpoints = scenario.get("checkpoints", [])
        if not checkpoints or len({cp["checkpoint_id"] for cp in checkpoints}) != len(checkpoints):
            raise EvaluationInputError(f"Missing or duplicate checkpoint: {sid}")
        for checkpoint in checkpoints:
            if checkpoint["after_event"] not in event_ids:
                raise EvaluationInputError(f"Checkpoint references a missing event: {sid}")
            available = set(event_ids[: event_ids.index(checkpoint["after_event"]) + 1])
            seen_facts, facts_by_id = set(), {}
            for fact in checkpoint["facts"]:
                _check_gold(fact, sources, available, sid)
                key = fact_key(fact)
                if key in seen_facts or fact["fact_id"] in facts_by_id:
                    raise EvaluationInputError(f"Duplicate gold fact at checkpoint: {sid}")
                seen_facts.add(key)
                facts_by_id[fact["fact_id"]] = fact
                annotation = (sid, fact["fact_id"])
                identity = (key, fingerprint(fact["evidence"]))
                if annotation in gold and gold[annotation] != identity:
                    raise EvaluationInputError(f"Gold fact identity changed across checkpoints: {sid}")
                if annotation not in gold:
                    gold[annotation] = identity
                    counts[language]["gold_facts"] += 1
            for question in checkpoint.get("questions", []):
                identity = (sid, question["question_id"])
                if identity in questions:
                    raise EvaluationInputError(f"Duplicate question identity: {sid}")
                questions.add(identity)
                support = question.get("supporting_fact_ids")
                if (
                    question["expected"] not in {"supported", "abstain"}
                    or not isinstance(support, list)
                    or bool(support) != (question["expected"] == "supported")
                ):
                    raise EvaluationInputError(f"Invalid question/support label: {sid}")
                for fid in support:
                    fact = facts_by_id.get(fid)
                    if (
                        fact is None
                        or fact["chat_id"] != question["chat_id"]
                        or question.get("target_subject_id", fact["subject_id"]) != fact["subject_id"]
                    ):
                        raise EvaluationInputError(f"Question cites out-of-scope/missing fact: {sid}")
                counts[language]["unknown_questions"] += int(question["expected"] == "abstain")
    totals = {key: sum(row[key] for row in counts.values()) for key in ("scenarios", "gold_facts", "unknown_questions")}
    sufficient = totals["scenarios"] >= 200 and totals["gold_facts"] >= 300 and totals["unknown_questions"] >= 100
    return {
        "totals": totals,
        "languages": counts,
        "unique_conversations": len(messages),
        "size_gate": sufficient,
        "sha256": fingerprint(corpus),
        "independent_review": "REVIEWED" if review == {"REVIEWED"} else "PENDING",
    }
