"""Project only executable inputs; the replay owner never receives scoring labels."""

import copy

from .contract import EvaluationInputError, fingerprint

EVENT_TYPES = frozenset(
    {
        "message",
        "edit",
        "admin_confirmation",
        "forget_user",
        "forget_source",
        "forget_group",
        "optout",
        "optin",
        "new_epoch",
        "learning_pause",
        "provider_failure",
        "provider_resume",
        "budget_pause",
        "pending_expiry",
        "advance_time",
        "task_replay",
    }
)
SOURCE_FIELDS = {
    "event_id",
    "type",
    "chat_id",
    "user_id",
    "message_id",
    "original_sent_at",
    "edited_at",
    "text",
    "is_bot",
    "forwarded",
    "quoted_spans",
}
CONTROL_FIELDS = {"event_id", "type", "chat_id", "user_id", "message_id", "seconds", "source_event"}
QUESTION_FIELDS = {"question_id", "chat_id", "requester_id", "target_subject_id", "text"}


def project_scenario(scenario):
    if scenario.get("synthetic") is not True or scenario.get("authorship") != "ai_authored":
        raise EvaluationInputError("This offline replay driver accepts the synthetic corpus only")
    events = []
    for event in scenario["events"]:
        if event.get("type") not in EVENT_TYPES:
            raise EvaluationInputError("Unsupported replay event; no silent no-op")
        fields = SOURCE_FIELDS if event["type"] in {"message", "edit", "admin_confirmation"} else CONTROL_FIELDS
        events.append({key: copy.deepcopy(value) for key, value in event.items() if key in fields})
    return {
        "scenario_id": scenario["scenario_id"],
        "language": scenario["language"],
        "learning_started_at": scenario["learning_started_at"],
        "events": events,
        "business_seed": copy.deepcopy(scenario["protected_business"]),
        "checkpoints": [
            {
                "checkpoint_id": cp["checkpoint_id"],
                "after_event": cp["after_event"],
                "questions": [
                    {k: copy.deepcopy(v) for k, v in q.items() if k in QUESTION_FIELDS} for q in cp.get("questions", [])
                ],
            }
            for cp in scenario["checkpoints"]
        ],
    }


def business_rows(chat_id, seed):
    """Real settings/stats/captcha row shapes with synthetic, fixed input values.

    Settings use the legacy table's pk/sk; counters and captcha use the stats
    table's sole stat_key. The scorer independently reconstructs these full rows.
    """
    return {
        "SETTINGS": {
            "pk": "CHAT#" + str(chat_id),
            "sk": "SETTINGS",
            "style_profile": {"tone": seed["SETTINGS"]},
            "updated_at": 2_000_000_000,
        },
        "CHAT_STATS": {
            "stat_key": str(chat_id),
            "total_joins": 23,
            "verified_users": 19,
            "total_bans": 4,
            "spam_bans": 2,
            "started_at": seed["CHAT_STATS"],
        },
        "CAPTCHA_PENDING": {
            "stat_key": f"captcha_pending#{chat_id}#{seed['CAPTCHA_PENDING']}",
            "generation": "0123456789abcdef0123456789abcdef",
            "revision": 3,
            "status": "pending",
            "join_msg_id": 23,
            "verify_msg_id": 24,
            "attempts": 1,
            "handled_message_ids": [25],
            "wrong_msg_ids": [25],
            "created_at": 2_000_000_000,
            "expires_at": 2_000_000_300,
            "ttl": 2_001_296_300,
            "action_done": False,
        },
    }


def business_hashes(chat_id, seed):
    return {key: fingerprint(row) for key, row in business_rows(chat_id, seed).items()}


def validate_projected(scenario):
    expected = {"scenario_id", "language", "learning_started_at", "events", "business_seed", "checkpoints"}
    if set(scenario) != expected:
        raise EvaluationInputError("Domain replay requires projected, label-free input")
    for event in scenario["events"]:
        fields = SOURCE_FIELDS if event.get("type") in {"message", "edit", "admin_confirmation"} else CONTROL_FIELDS
        if event.get("type") not in EVENT_TYPES or not set(event) <= fields:
            raise EvaluationInputError("Unsupported event or non-input annotation reached replay")
    for checkpoint in scenario["checkpoints"]:
        if set(checkpoint) != {"checkpoint_id", "after_event", "questions"} or any(
            not set(question) <= QUESTION_FIELDS for question in checkpoint["questions"]
        ):
            raise EvaluationInputError("Scoring labels must not reach the adapter")
