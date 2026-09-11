"""A visibly limited toy provider fixture author, reading executable inputs only.

This is not the production extractor or an evaluation oracle. These deterministic
responses exercise runtime plumbing; omissions/poor language normalisation are
expected. Review/replace this separate fixture file to exercise other responses.
"""

import re

from .fixture_provider import text_hash

TECH = re.compile(
    r"\b(Python|PostgreSQL|Redis|Rust|Kotlin|SQLite|Figma|Go|Docker|R|Java|TypeScript|Julia|Ruby|Elixir|Erlang)\b"
)
DECLARATIONS = re.compile(
    r"\b(?:I (?:use|also use|write)|я (?:использую|пользуюсь|пишу))\b|қолдан|код жазамын|сервистер жазамын", re.I
)
QUESTION_FIELDS = {
    "location": ("city", "городе", "қалада"),
    "occupation": ("occupation", "профессия", "мамандығы"),
    "current_project": ("project", "проектом", "жоба"),
    "education": ("studied", "специальность", "оқығанын"),
    "interests": ("hobby", "хобби"),
}


def _changes(text):
    """Deliberately covers technology only; quality scores must expose omissions."""
    if not DECLARATIONS.search(text):
        return []
    action = "remove" if re.search(r"no longer|больше не|қолданбаймын", text, re.I) else "assert"
    return [
        {
            "field": "tech_stack",
            "value": value,
            "evidence": text,
            "action": action,
            "facet": "",
            "attribution": "self_explicit",
        }
        for value in dict.fromkeys(TECH.findall(text))
    ]


def author_fixture_rows(inputs):
    """Accept project_scenario output, never inspect checkpoint facts or labels."""
    rows = {}

    def add(kind, text, response):
        key = kind, text_hash(text)
        row = {"kind": kind, "input_text": text, "input_sha256": key[1], "response": response}
        if key in rows and rows[key] != row:
            if kind == "confirmation" and rows[key]["response"]["changes"] == response["changes"]:
                response["authorized_actor_ids"] = sorted(
                    set(rows[key]["response"]["authorized_actor_ids"] + response["authorized_actor_ids"])
                )
            else:
                raise ValueError("Fixture input has contradictory independent responses")
        rows[key] = row

    for scenario in inputs:
        if "business_seed" not in scenario or "protected_business" in scenario:
            raise ValueError("Fixture author accepts only projected executable inputs")
        for event in scenario["events"]:
            if "text" not in event:
                continue
            text = event["text"]
            add("extraction", text, {"facts": _changes(text)})
            if event["type"] == "admin_confirmation":
                # Separate explicit command fixture; no model receives group facts.
                phrase = text.split(":", 1)[-1].strip().rstrip(".")
                add(
                    "confirmation",
                    text,
                    {
                        "authorized_actor_ids": [event["user_id"]],
                        "changes": [{"field": "rule", "value": phrase, "start": 0, "end": len(text)}],
                    },
                )
        for cp in scenario["checkpoints"]:
            if "facts" in cp:
                raise ValueError("Fixture author must not receive labels")
            for question in cp["questions"]:
                text = question["text"]
                fields = [
                    name for name, words in QUESTION_FIELDS.items() if any(word in text.lower() for word in words)
                ]
                add("answer", text, {"fields": fields or ["*"]})
    return [rows[key] for key in sorted(rows)]
