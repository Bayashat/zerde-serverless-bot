"""No extra Lambda, exact read-only monitor scope and compact resolved inventory."""

import json

from tests.test_infra_configuration import _find_resource_by_property, _template


def test_shared_inventory_fits_environment_and_monitor_is_only_on_prod(monkeypatch):
    monkeypatch.setenv("MEMORY_COST_METERING_STARTED_AT", "1789000000")
    for environment in ("dev", "prod"):
        template = _template(monkeypatch, env_name=environment)
        assert len(template.find_resources("AWS::Lambda::Function")) == 6
        variables = []
        for kind in ("bot", "memory-v2-worker"):
            _, function = _find_resource_by_property(
                template, "AWS::Lambda::Function", "FunctionName", f"zerde-serverless-{kind}-{environment}"
            )
            env = function["Properties"]["Environment"]["Variables"]
            variables.append(env)
            assert env["MEMORY_COST_INSTRUMENTATION_SCHEMA"] == "1"
            # CloudFormation tokens add representation overhead, so this is conservative.
            assert sum(len(key.encode()) + len(json.dumps(value).encode()) for key, value in env.items()) < 4096
            assert '"alarm_count":10' in json.dumps(env["MEMORY_COST_INVENTORY"]).replace('\\"', '"')
        assert variables[0]["MEMORY_COST_INVENTORY"] == variables[1]["MEMORY_COST_INVENTORY"]
        rules = [
            row
            for row in template.find_resources("AWS::Events::Rule").values()
            if "MONITOR_MEMORY_V2_COST" in json.dumps(row)
        ]
        assert len(rules) == (1 if environment == "prod" else 0)
        if rules:
            assert rules[0]["Properties"]["State"] == "ENABLED"
            assert rules[0]["Properties"]["ScheduleExpression"] == "rate(1 hour)"
            assert rules[0]["Properties"]["Targets"][0]["RetryPolicy"]["MaximumRetryAttempts"] == 0


def test_first_deployment_has_explicit_metering_epoch_gate(monkeypatch):
    monkeypatch.setenv("MEMORY_COST_METERING_STARTED_AT", "0")
    template = _template(monkeypatch, env_name="prod")
    rule = next(
        row
        for row in template.find_resources("AWS::Events::Rule").values()
        if "MONITOR_MEMORY_V2_COST" in json.dumps(row)
    )
    assert rule["Properties"]["State"] == "DISABLED"
