"""Adapter seam for future domain replay; the built-in adapter is visibly an oracle."""

import copy
from typing import Protocol


class ObservationAdapter(Protocol):
    """Later Z08/Z09 integration may replay scenarios into their real local owners."""

    provider_kind: str

    def observe_scenario(self, scenario: dict) -> list[dict]: ...


def collect_observations(corpus, adapter: ObservationAdapter):
    if adapter.provider_kind not in {"fake_provider", "recorded_provider", "synthetic_oracle"}:
        raise ValueError("Offline adapter must declare its evidence kind")
    from .replay_input import project_scenario

    return [
        record
        for scenario in corpus
        for record in adapter.observe_scenario(
            project_scenario(scenario) if getattr(adapter, "requires_projected_input", False) else scenario
        )
    ]


class OracleSelfCheck:
    """Copies gold solely to test evaluator bookkeeping, never to evaluate a model."""

    provider_kind = "synthetic_oracle"

    def observe_scenario(self, scenario):
        records = []
        for checkpoint in scenario["checkpoints"]:
            facts = copy.deepcopy(checkpoint["facts"])
            answers = []
            for question in checkpoint.get("questions", []):
                assertions = [
                    copy.deepcopy(fact) for fact in facts if fact["fact_id"] in question.get("supporting_fact_ids", [])
                ]
                answers.append(
                    {
                        "question_id": question["question_id"],
                        "abstained": question["expected"] == "abstain",
                        "assertions": assertions,
                    }
                )
            records.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "checkpoint_id": checkpoint["checkpoint_id"],
                    "facts": facts,
                    "answers": answers,
                    "traces": {
                        "business_before": copy.deepcopy(scenario["protected_business"]),
                        "business_after": copy.deepcopy(scenario["protected_business"]),
                        "sent_actions": [],
                        "safety_surfaces": {"raw": [], "context": [], "logs": [], "answers": []},
                        "work": [],
                    },
                }
            )
        return records
