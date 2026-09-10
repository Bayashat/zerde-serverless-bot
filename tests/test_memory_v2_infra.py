"""Storage wiring contracts; these template tests do not prove Lambda packaging."""

import sys
from pathlib import Path

from aws_cdk import App, Stack
from aws_cdk.assertions import Template

sys.path.append(str(Path("infra").resolve()))
from components.memory_v2 import MemoryV2Construct  # noqa: E402


def test_v2_storage_is_independent_and_protected_in_production():
    stack = Stack(App(), "MemoryTest")
    MemoryV2Construct(stack, "Memory", env_name="prod", is_prod=True)
    template = Template.from_stack(stack)
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "zerde-serverless-memory-v2-prod",
            "BillingMode": "PAY_PER_REQUEST",
            "DeletionProtectionEnabled": True,
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True,
                "RecoveryPeriodInDays": 7,
            },
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "work-due",
                    "KeySchema": [
                        {"AttributeName": "work_queue", "KeyType": "HASH"},
                        {"AttributeName": "due_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "KEYS_ONLY"},
                }
            ],
        },
    )
    table = next(iter(template.find_resources("AWS::DynamoDB::Table").values()))
    assert table["DeletionPolicy"] == "Retain"
    assert table["UpdateReplacePolicy"] == "Retain"
    # No custom-resource seed, schedule or queue activates a new chat in Z05.
    assert set(r["Type"] for r in template.to_json()["Resources"].values()) == {"AWS::DynamoDB::Table"}


def test_absent_v2_configuration_does_not_use_legacy_table(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("memory_v2_bot_app", Path("src/bot/app.py"))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    monkeypatch.setattr(app, "MEMORY_V2_TABLE_NAME", None)
    monkeypatch.setattr(app, "MEMORY_TABLE_NAME", "legacy-business-table")
    monkeypatch.setattr(app, "_memory_v2_repo", None)
    assert app.get_memory_v2_repo() is None
