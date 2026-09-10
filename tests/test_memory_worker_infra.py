"""Separate queue and project-wide budget IAM must survive stack composition."""

import json

from tests.test_infra_configuration import _find_resource_by_property, _template


def test_worker_timeout_queue_lease_and_recovery_are_bounded(monkeypatch):
    template = _template(monkeypatch, env_name="prod")
    _, worker = _find_resource_by_property(
        template, "AWS::Lambda::Function", "FunctionName", "zerde-serverless-memory-v2-worker-prod"
    )
    _, queue = _find_resource_by_property(
        template, "AWS::SQS::Queue", "QueueName", "zerde-serverless-memory-v2-queue-prod"
    )
    _, rule = _find_resource_by_property(
        template, "AWS::Events::Rule", "Name", "zerde-serverless-memory-v2-recovery-prod"
    )
    assert worker["Properties"]["Timeout"] == 120
    assert worker["Properties"]["ReservedConcurrentExecutions"] == 2
    assert queue["Properties"]["VisibilityTimeout"] >= 6 * 120 + 20
    assert rule["Properties"]["ScheduleExpression"] == "rate(5 minutes)"
    assert json.loads(rule["Properties"]["Targets"][0]["Input"]) == {"schema": 2, "task_type": "RECOVER_MEMORY_V2"}


def test_dev_budget_targets_prod_cost_keys_without_prod_profile_access(monkeypatch):
    template = _template(monkeypatch, env_name="dev")
    for slug in ("bot", "memory-v2-worker"):
        _, worker = _find_resource_by_property(
            template, "AWS::Lambda::Function", "FunctionName", f"zerde-serverless-{slug}-dev"
        )
        variables = worker["Properties"]["Environment"]["Variables"]
        assert variables["MEMORY_BUDGET_TABLE_NAME"] == "zerde-serverless-memory-v2-prod"
        assert variables["MEMORY_V2_TABLE_NAME"] != variables["MEMORY_BUDGET_TABLE_NAME"]
        assert variables["MEMORY_V2_QUEUE_URL"]
        role = worker["Properties"]["Role"]["Fn::GetAtt"][0]
        statements = [
            statement
            for policy in template.find_resources("AWS::IAM::Policy").values()
            if {"Ref": role} in policy["Properties"].get("Roles", [])
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]
            if "zerde-serverless-memory-v2-prod" in json.dumps(statement.get("Resource"))
        ]
        assert statements
        for statement in statements:
            assert statement["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] == [
                "MEMORY_BUDGET#*",
                "MEMORY_ATTEMPT#*",
            ]
            assert "dynamodb:Scan" not in statement["Action"]
