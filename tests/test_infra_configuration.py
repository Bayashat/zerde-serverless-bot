import json
import re
import runpy
import sys
from pathlib import Path
from typing import Any

import pytest
from aws_cdk import App
from aws_cdk import aws_lambda as lambda_
from aws_cdk.assertions import Template

INFRA_DIR = Path("infra").resolve()
if str(INFRA_DIR) not in sys.path:
    sys.path.append(str(INFRA_DIR))

from components import bot as bot_component  # noqa: E402
from components import memory_worker as memory_worker_component  # noqa: E402
from components import news as news_component  # noqa: E402
from components import operations as operations_component  # noqa: E402
from components import quiz as quiz_component  # noqa: E402
from stack import ZerdeTelegramBotStack  # noqa: E402

_CONFIG_DEFAULTS = {
    "MAIN_TASK_QUEUE_RETENTION_DAYS": "1",
    "MAIN_TASK_DLQ_RETENTION_DAYS": "14",
    "AGENT_BOT_ID": "",
    "MULTIMODAL_ENABLED": "true",
    "MULTIMODAL_MAX_DOWNLOAD_BYTES": "12000000",
    "MULTIMODAL_INLINE_MAX_BYTES": "8000000",
    "MULTIMODAL_TEXT_FILE_MAX_CHARS": "20000",
}
_ACTIVE_RUNTIME_CONFIG_KEYS = {
    "AGENT_BOT_ID",
    "MULTIMODAL_ENABLED",
    "MULTIMODAL_MAX_DOWNLOAD_BYTES",
    "MULTIMODAL_INLINE_MAX_BYTES",
    "MULTIMODAL_TEXT_FILE_MAX_CHARS",
}
_QUEUE_CONFIG_KEYS = {
    "MAIN_TASK_QUEUE_RETENTION_DAYS",
    "MAIN_TASK_DLQ_RETENTION_DAYS",
}


def test_production_news_preserves_chinese_suspension_without_disabling_other_languages(monkeypatch: Any) -> None:
    for lang, chat in (("KK", "-1000000000001"), ("ZH", "-1000000000002"), ("RU", "-1000000000003")):
        monkeypatch.setenv(f"CHATS_{lang}", chat)
    template = _template(monkeypatch, env_name="prod")
    rules = {
        r["Properties"]["Name"]: r["Properties"]
        for r in template.find_resources("AWS::Events::Rule").values()
        if r["Properties"].get("Name", "").startswith("zerde-serverless-news-")
    }
    assert set(rules) == {
        "zerde-serverless-news-kk-0400-prod",
        "zerde-serverless-news-zh-0405-prod",
        "zerde-serverless-news-ru-0410-prod",
    }
    for name, rule in rules.items():
        lang = name.split("-")[3]
        assert rule["State"] == ("DISABLED" if lang == "zh" else "ENABLED")
        assert len(rule["Targets"]) == 1


def _workflow_variables(filename: str) -> dict[str, str]:
    return dict(
        re.findall(
            r"^\s+([A-Z][A-Z0-9_]+): (\$\{\{ vars\.[^\n]+)",
            Path(".github/workflows", filename).read_text(),
            re.MULTILINE,
        )
    )


def _runtime_value_as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def test_deploy_and_preview_map_the_same_variables_and_defaults() -> None:
    deploy = _workflow_variables("deploy.yml")
    preview = _workflow_variables("pr_check.yml")
    assert preview == deploy
    defaults = {
        **_CONFIG_DEFAULTS,
        "CAPTCHA_TIMEOUT_SECONDS": "120",
        "KICK_BAN_DURATION_SECONDS": "60",
        "VOTEBAN_THRESHOLD": "7",
        "VOTEBAN_FORGIVE_THRESHOLD": "7",
        "GEMINI_RPD_LIMIT": "500",
        "QUIZ_LLM_RPD": "20",
        "GEMINI_MODEL": "gemini-3.1-flash-lite",
        "NEWS_GEMINI_MODEL": "gemini-3.1-flash-lite",
        "QUIZ_GEMINI_MODEL": "gemini-3.1-flash-lite",
        "DEEPSEEK_MODEL": "deepseek-chat",
    }
    for key, value in defaults.items():
        fallback = f" || '{value}'" if value else ""
        assert deploy[key] == "${{ vars." + key + fallback + " }}"
    for unused in ("AI_PROVIDER", "WTF_GEMINI_MODEL", "FALLBACK_MODEL"):
        assert unused not in deploy


def test_config_defaults_agree_between_example_runtime_and_lambda_template(monkeypatch: Any) -> None:
    for key in _CONFIG_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    runtime = runpy.run_path("src/bot/core/config.py")
    example = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", Path(".env.example").read_text(), re.MULTILINE))
    template = _dev_template(monkeypatch)
    _, bot = _find_resource_by_property(template, "AWS::Lambda::Function", "FunctionName", "zerde-serverless-bot-dev")
    deployed = bot["Properties"]["Environment"]["Variables"]
    for key, expected in _CONFIG_DEFAULTS.items():
        assert example[key] == expected, key
        if key not in _QUEUE_CONFIG_KEYS:
            assert deployed[key] == expected, key
            if key in _ACTIVE_RUNTIME_CONFIG_KEYS:
                assert _runtime_value_as_text(runtime[key]) == expected, key
            else:
                assert key not in runtime, key


def test_typed_config_overrides_reach_bot_runtime(monkeypatch: Any) -> None:
    overrides = {
        "AGENT_BOT_ID": "12345",
        "MULTIMODAL_ENABLED": "false",
        "MULTIMODAL_MAX_DOWNLOAD_BYTES": "9000000",
        "MULTIMODAL_INLINE_MAX_BYTES": "6000000",
        "MULTIMODAL_TEXT_FILE_MAX_CHARS": "15000",
    }
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    runtime = runpy.run_path("src/bot/core/config.py")
    template = _dev_template(monkeypatch)
    for name in ("zerde-serverless-bot-dev",):
        _, function = _find_resource_by_property(template, "AWS::Lambda::Function", "FunctionName", name)
        deployed = function["Properties"]["Environment"]["Variables"]
        for key, expected in overrides.items():
            assert deployed[key] == expected, (name, key)
            if key in _ACTIVE_RUNTIME_CONFIG_KEYS:
                assert _runtime_value_as_text(runtime[key]) == expected, key
            else:
                assert key not in runtime, key


def _stub_python_function(scope: Any, construct_id: str, **kwargs: Any) -> lambda_.Function:
    function_kwargs = {
        "architecture": kwargs.get("architecture"),
        "environment": kwargs.get("environment"),
        "function_name": kwargs.get("function_name"),
        "layers": kwargs.get("layers"),
        "memory_size": kwargs.get("memory_size"),
        "runtime": kwargs["runtime"],
        "timeout": kwargs.get("timeout"),
        "reserved_concurrent_executions": kwargs.get("reserved_concurrent_executions"),
        "dead_letter_queue": kwargs.get("dead_letter_queue"),
        "retry_attempts": kwargs.get("retry_attempts"),
        "max_event_age": kwargs.get("max_event_age"),
    }
    return lambda_.Function(
        scope,
        construct_id,
        handler="index.handler",
        code=lambda_.Code.from_inline("def handler(event, context):\n    return None\n"),
        **{key: value for key, value in function_kwargs.items() if value is not None},
    )


def test_all_five_functions_filter_local_python_caches(monkeypatch: Any) -> None:
    from components.constants import LAMBDA_BUNDLING

    seen = set()
    original_stub = _stub_python_function

    def capture(scope, construct_id, **kwargs):
        assert kwargs["bundling"] is LAMBDA_BUNDLING
        assert set(kwargs["bundling"].asset_excludes) == {"__pycache__", "*.pyc", "*.pyo"}
        seen.add(kwargs["function_name"])
        return original_stub(scope, construct_id, **kwargs)

    monkeypatch.setattr(sys.modules[__name__], "_stub_python_function", capture)
    _dev_template(monkeypatch)
    assert seen == {
        f"zerde-serverless-{name}-dev" for name in ("bot", "news", "quiz", "operations", "memory-v2-worker")
    }


def _template(monkeypatch: Any, *, env_name: str) -> Template:
    # Tests provide synthetic configuration; never load a developer's real .env.
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(memory_worker_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(operations_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(bot_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(news_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(quiz_component, "PythonFunction", _stub_python_function)

    app = App()
    stack = ZerdeTelegramBotStack(app, "TestStack", env_name=env_name)
    return Template.from_stack(stack)


def _dev_template(monkeypatch: Any) -> Template:
    return _template(monkeypatch, env_name="dev")


def _resources(template: Template) -> dict[str, Any]:
    return template.to_json()["Resources"]


def _find_resource_by_property(
    template: Template,
    resource_type: str,
    property_name: str,
    property_value: str,
) -> tuple[str, dict[str, Any]]:
    for logical_id, resource in _resources(template).items():
        if resource.get("Type") != resource_type:
            continue
        if resource.get("Properties", {}).get(property_name) == property_value:
            return logical_id, resource
    raise AssertionError(f"Missing {resource_type} with {property_name}={property_value}")


def _event_source_targets(template: Template, queue_logical_id: str) -> list[Any]:
    queue_arn = {"Fn::GetAtt": [queue_logical_id, "Arn"]}
    targets: list[Any] = []
    for resource in _resources(template).values():
        if resource.get("Type") != "AWS::Lambda::EventSourceMapping":
            continue
        properties = resource.get("Properties", {})
        if properties.get("EventSourceArn") == queue_arn:
            targets.append(properties.get("FunctionName"))
    return targets


def _function_role_id(function_resource: dict[str, Any]) -> str:
    role = function_resource["Properties"]["Role"]
    return role["Fn::GetAtt"][0]


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value]


def _role_statements(template: Template, role_logical_id: str) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    for resource in _resources(template).values():
        if resource.get("Type") != "AWS::IAM::Policy":
            continue
        properties = resource.get("Properties", {})
        if {"Ref": role_logical_id} not in _as_list(properties.get("Roles", [])):
            continue
        policy_statements = properties["PolicyDocument"]["Statement"]
        statements.extend(_as_list(policy_statements))
    return statements


def _role_has_action_on_queue(
    template: Template,
    role_logical_id: str,
    actions: set[str],
    queue_logical_id: str,
) -> bool:
    queue_arn = {"Fn::GetAtt": [queue_logical_id, "Arn"]}
    for statement in _role_statements(template, role_logical_id):
        statement_actions = set(_as_list(statement.get("Action", [])))
        if actions.isdisjoint(statement_actions):
            continue
        if queue_arn in _as_list(statement.get("Resource", [])):
            return True
    return False


def _role_actions_for_service(template: Template, role_logical_id: str, service_prefix: str) -> set[str]:
    actions: set[str] = set()
    for statement in _role_statements(template, role_logical_id):
        for action in _as_list(statement.get("Action", [])):
            if isinstance(action, str) and action.startswith(f"{service_prefix}:"):
                actions.add(action)
    return actions


def test_main_and_v2_queues_have_separate_lambda_consumers(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)
    bot_lambda_id, _ = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )
    memory_worker_lambda_id, _ = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-memory-v2-worker-dev",
    )
    main_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-queue-dev",
    )
    v2_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-memory-v2-queue-dev",
    )

    assert _event_source_targets(template, main_queue_id) == [{"Ref": bot_lambda_id}]
    assert _event_source_targets(template, v2_queue_id) == [{"Ref": memory_worker_lambda_id}]


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_retired_contest_has_no_schedule_or_iam_queue_grant(monkeypatch, env_name):
    template = _template(monkeypatch, env_name=env_name)
    assert "contest" not in json.dumps(template.to_json()).lower()
    _find_resource_by_property(
        template, "AWS::SQS::Queue", "QueueName", f"zerde-serverless-timeout-tasks-queue-{env_name}"
    )
    _find_resource_by_property(template, "AWS::DynamoDB::Table", "TableName", f"zerde-serverless-memory-v2-{env_name}")


@pytest.mark.parametrize("env_name", ["dev", "prod"])
@pytest.mark.parametrize("legacy_memory_enabled", ["true", "false"])
def test_retired_daily_summary_cannot_be_recreated_by_legacy_settings(monkeypatch, env_name, legacy_memory_enabled):
    # A non-empty chat map used to recreate this retired schedule even with
    # GROUP_MEMORY_ENABLED=false. Preserve the active business/recovery owners.
    monkeypatch.setenv("CHATS_KK", "-100123")
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("GROUP_MEMORY_ENABLED", legacy_memory_enabled)
    template = _template(monkeypatch, env_name=env_name)
    rendered = json.dumps(template.to_json())
    assert "PROCESS_DAILY_GROUP_SUMMARIES" not in rendered
    assert "DailyGroupSummaryRule" not in rendered  # Includes its former SQS policy grant.
    assert "group-memory-daily-summary" not in rendered
    for table in ("bot-stats", "memory-v2", "quiz"):
        _, resource = _find_resource_by_property(
            template, "AWS::DynamoDB::Table", "TableName", f"zerde-serverless-{table}-{env_name}"
        )
        if env_name == "prod":
            assert resource["DeletionPolicy"] == "Retain"
            assert resource["Properties"]["DeletionProtectionEnabled"] is True
    for queue in ("timeout-tasks-queue", "memory-v2-queue"):
        _find_resource_by_property(template, "AWS::SQS::Queue", "QueueName", f"zerde-serverless-{queue}-{env_name}")
    for rule in ("memory-v2-recovery", "quiz-answer-recovery", "quiz-publication-recovery"):
        _find_resource_by_property(template, "AWS::Events::Rule", "Name", f"zerde-serverless-{rule}-{env_name}")
    if env_name == "prod":
        for rule in ("news-kk-0400", "quiz-kk-0800", "quiz-bank-builder-0730"):
            _find_resource_by_property(template, "AWS::Events::Rule", "Name", f"zerde-serverless-{rule}-prod")


def test_sqs_queue_retention_defaults_are_operationally_safe(monkeypatch: Any) -> None:
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)
    for key in (
        "MAIN_TASK_QUEUE_RETENTION_DAYS",
        "MAIN_TASK_DLQ_RETENTION_DAYS",
    ):
        monkeypatch.delenv(key, raising=False)

    template = _dev_template(monkeypatch)
    _, main_queue = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-queue-dev",
    )
    _, main_dlq = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-dlq-dev",
    )

    assert main_queue["Properties"]["MessageRetentionPeriod"] == 86_400
    assert main_dlq["Properties"]["MessageRetentionPeriod"] == 1_209_600


def test_sqs_queue_retention_is_configurable_from_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("MAIN_TASK_QUEUE_RETENTION_DAYS", "2")
    monkeypatch.setenv("MAIN_TASK_DLQ_RETENTION_DAYS", "3")

    template = _dev_template(monkeypatch)
    _, main_queue = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-queue-dev",
    )
    _, main_dlq = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-dlq-dev",
    )

    assert main_queue["Properties"]["MessageRetentionPeriod"] == 172_800
    assert main_dlq["Properties"]["MessageRetentionPeriod"] == 259_200


def test_bot_environment_preserves_explicit_providers_and_media(monkeypatch: Any) -> None:
    for key in (
        "DEEPSEEK_API_BASE",
        "DEEPSEEK_MODEL",
        "GROQ_MODEL",
        "GROQ_SPAM_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)

    template = _dev_template(monkeypatch)
    _, bot_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )

    env_vars = bot_lambda["Properties"]["Environment"]["Variables"]
    assert env_vars["GROQ_MODEL"] == "openai/gpt-oss-120b"
    assert env_vars["GROQ_SPAM_MODEL"] == "openai/gpt-oss-safeguard-20b"
    assert env_vars["DEEPSEEK_API_BASE"] == "https://api.deepseek.com"
    assert env_vars["DEEPSEEK_MODEL"] == "deepseek-chat"
    assert env_vars["MULTIMODAL_ENABLED"] == "true"
    assert env_vars["MULTIMODAL_MAX_DOWNLOAD_BYTES"] == "12000000"
    assert env_vars["MULTIMODAL_INLINE_MAX_BYTES"] == "8000000"
    assert env_vars["MULTIMODAL_TEXT_FILE_MAX_CHARS"] == "20000"


def test_synthesizes_main_dlq_visible_alarm(monkeypatch: Any) -> None:
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    template = _dev_template(monkeypatch)

    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "zerde-serverless-timeout-tasks-dlq-visible-dev",
            "MetricName": "ApproximateNumberOfMessagesVisible",
            "Namespace": "AWS/SQS",
            "Threshold": 1,
        },
    )


def test_idle_dev_stops_ingress_and_consumers_without_alarm_spend(monkeypatch):
    monkeypatch.delenv("DEV_RUNTIME_ENABLED", raising=False)
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)
    template = _dev_template(monkeypatch)
    functions = template.find_resources("AWS::Lambda::Function")
    assert len(functions) == 5
    assert all(fn["Properties"]["ReservedConcurrentExecutions"] == 0 for fn in functions.values())
    mappings = template.find_resources("AWS::Lambda::EventSourceMapping")
    assert len(mappings) == 2
    assert all(mapping["Properties"]["Enabled"] is False for mapping in mappings.values())
    # Lambda validates SQS limits even when the mapping is disabled.
    assert all("ScalingConfig" not in mapping["Properties"] for mapping in mappings.values())
    assert not template.find_resources("AWS::CloudWatch::Alarm")


def test_active_runtime_registers_private_alarm_and_recovery_actions(monkeypatch):
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    template = _dev_template(monkeypatch)
    mappings = template.find_resources("AWS::Lambda::EventSourceMapping")
    assert all(mapping["Properties"]["Enabled"] is True for mapping in mappings.values())
    assert sorted(mapping["Properties"]["ScalingConfig"]["MaximumConcurrency"] for mapping in mappings.values()) == [
        2,
        10,
    ]
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    assert len(alarms) == 18
    for alarm in alarms.values():
        props = alarm["Properties"]
        assert len(props["AlarmActions"]) == 1
        assert props["OKActions"] == props["AlarmActions"]
    _, notifier = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-operations-dev",
    )
    variables = notifier["Properties"]["Environment"]["Variables"]
    assert len(json.loads(variables["OPERATIONS_ALARM_NAMES"])) == 18
    assert notifier["Properties"]["Timeout"] == 60
    assert "DeadLetterConfig" in notifier["Properties"]
    subscription = next(iter(template.find_resources("AWS::SNS::Subscription").values()))
    assert "RedrivePolicy" in subscription["Properties"]
    statements = _role_statements(template, _function_role_id(notifier))
    ssm = [s for s in statements if "ssm:GetParameters" in _as_list(s.get("Action", []))]
    assert "bot-token" in repr(ssm) and "gemini-api-key" not in repr(ssm)
    ddb = [s for s in statements if "dynamodb:UpdateItem" in _as_list(s.get("Action", []))]
    assert ddb[0]["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] == ["operations#*"]


def test_prod_ignores_dev_idle_flag_preserves_active_limits_and_enables_quiz_pitr(monkeypatch):
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("KICK_BAN_DURATION_SECONDS", "31")
    template = _template(monkeypatch, env_name="prod")
    _, quiz = _find_resource_by_property(
        template,
        "AWS::DynamoDB::Table",
        "TableName",
        "zerde-serverless-quiz-prod",
    )
    assert quiz["Properties"]["PointInTimeRecoverySpecification"] == {
        "PointInTimeRecoveryEnabled": True,
        "RecoveryPeriodInDays": 7,
    }
    assert quiz["Properties"]["DeletionProtectionEnabled"] is True
    assert quiz["DeletionPolicy"] == "Retain"
    _, bot = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-prod",
    )
    assert "ReservedConcurrentExecutions" not in bot["Properties"]
    assert bot["Properties"]["Environment"]["Variables"]["KICK_BAN_DURATION_SECONDS"] == "60"
    for mapping in template.find_resources("AWS::Lambda::EventSourceMapping").values():
        assert mapping["Properties"]["Enabled"] is True
    assert sorted(
        m["Properties"]["ScalingConfig"]["MaximumConcurrency"]
        for m in template.find_resources("AWS::Lambda::EventSourceMapping").values()
    ) == [2, 10]
    assert len(template.find_resources("AWS::CloudWatch::Alarm")) == 18
    tags = {tag["Key"]: tag["Value"] for tag in quiz["Properties"]["Tags"]}
    assert tags == {"Project": "ZerdeBot", "Environment": "prod", "Component": "quiz"}


def _resolved_lambda_environment(template: Template, name: str) -> dict[str, str]:
    """Resolve the actual supported Ref/Join shapes, not short token placeholders."""
    account, region = "111122223333", "eu-central-1"
    resources = _resources(template)
    references = {"AWS::AccountId": account, "AWS::Region": region, "AWS::Partition": "aws"}
    for logical, resource in resources.items():
        props = resource.get("Properties", {})
        kind = resource["Type"]
        if kind == "AWS::DynamoDB::Table":
            references[logical] = props["TableName"]
        elif kind == "AWS::SQS::Queue":
            references[logical] = f"https://sqs.{region}.amazonaws.com/{account}/{props['QueueName']}"
        elif kind == "AWS::SNS::Topic":
            references[logical] = f"arn:aws:sns:{region}:{account}:{props['TopicName']}"
        elif kind == "AWS::Lambda::Function":
            references[logical] = props["FunctionName"]

    def resolve(value):
        if isinstance(value, str):
            return value
        assert isinstance(value, dict), "Environment values must resolve to strings"
        if set(value) == {"Ref"}:
            return references[value["Ref"]]
        assert set(value) == {"Fn::Join"}, "Unreviewed intrinsic requires real size accounting"
        separator, pieces = value["Fn::Join"]
        return separator.join(resolve(piece) for piece in pieces)

    _, function = _find_resource_by_property(template, "AWS::Lambda::Function", "FunctionName", name)
    return {key: resolve(value) for key, value in function["Properties"]["Environment"]["Variables"].items()}


@pytest.mark.parametrize("env_name", ["prod", "dev"])
def test_resolved_bot_environment_keeps_serialized_capacity_headroom(monkeypatch: Any, env_name: str) -> None:
    monkeypatch.setenv("CHATS_KK", "-1000000000001,-1000000000002")
    monkeypatch.setenv("CHATS_ZH", "-1000000000003,-1000000000004")
    monkeypatch.setenv("CHATS_RU", "")
    monkeypatch.setenv("AGENT_BOT_USERNAME", "b" * 32)
    monkeypatch.setenv("AGENT_BOT_ID", "1234567890123456")
    monkeypatch.setenv("ADMIN_USER_ID", "1234567890123456")
    monkeypatch.setenv("MEMORY_COST_METERING_STARTED_AT", "1789134091")
    template = _template(monkeypatch, env_name=env_name)
    resolved = _resolved_lambda_environment(template, f"zerde-serverless-bot-{env_name}")
    assert len(json.loads(resolved["CHAT_LANG_MAP"])) == 4
    assert resolved["QUEUE_URL"].startswith("https://sqs.eu-central-1.amazonaws.com/111122223333/")
    assert resolved["MEMORY_V2_QUEUE_URL"].endswith(f"memory-v2-queue-{env_name}")
    inventory = json.loads(resolved["MEMORY_COST_INVENTORY"])
    assert inventory["account_id"] == "111122223333"
    # Count the serialized wrapper, quoting, escaped nested JSON and whitespace.
    # The earlier sum(len(key)+len(value)) missed this overhead and passed a
    # production environment that AWS measured as 4114 bytes (>4096).
    serialized_bytes = len(json.dumps({"Variables": resolved}, ensure_ascii=True).encode("utf-8"))
    assert serialized_bytes <= 3500, serialized_bytes


_RETIRED_ENV_KEYS = (
    "MEMORY_TABLE_NAME",
    "VECTOR_MEMORY_QUEUE_URL",
    "GROUP_MEMORY_ENABLED",
    "GROUP_MEMORY_RECENT_LIMIT",
    "GROUP_MEMORY_RETENTION_DAYS",
    "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS",
    "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS",
    "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS",
    "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS",
    "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS",
    "GROUP_MEMORY_EXTRACTOR_PROVIDER",
    "GROUP_MEMORY_EXTRACTOR_MODE",
    "GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE",
    "GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT",
    "GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT",
    "GROUP_MEMORY_DAILY_SUMMARY_DAYS",
    "GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT",
    "VECTOR_MEMORY_ENABLED",
    "VECTOR_MEMORY_PROVIDER",
    "VECTOR_MEMORY_VECTOR_BUCKET_NAME",
    "VECTOR_MEMORY_INDEX_NAME",
    "VECTOR_MEMORY_DIMENSIONS",
    "VECTOR_MEMORY_EMBEDDING_MODEL",
    "VECTOR_MEMORY_SCHEMA_VERSION",
    "VECTOR_MEMORY_INDEX_THROTTLE_SECONDS",
    "VECTOR_MEMORY_BACKFILL_BATCH_SIZE",
    "VECTOR_MEMORY_MAX_DISTANCE",
    "AGENT_ENABLED",
    "AGENT_RECENT_CONTEXT_LIMIT",
    "AGENT_DAILY_PROACTIVE_LIMIT",
    "AGENT_PROACTIVE_DELAY_SECONDS",
    "AGENT_PROACTIVE_FINAL_THRESHOLD",
    "AGENT_PROACTIVE_DECISION_GROQ_MODELS",
    "AGENT_PROACTIVE_DECISION_CONTEXT_CHARS",
    "AGENT_PROACTIVE_DECISION_ALLOW_DEEPSEEK_FALLBACK",
    "AMBIENT_REACTIONS_ENABLED",
    "AMBIENT_REACTIONS_SAMPLE_RATE",
    "AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD",
    "AMBIENT_REACTIONS_DECISION_GROQ_MODELS",
    "AMBIENT_REACTIONS_DECISION_CONTEXT_CHARS",
    "AMBIENT_REACTIONS_MIN_GAP_PER_CHAT_SECONDS",
    "AMBIENT_REACTIONS_MIN_GAP_PER_USER_SECONDS",
    "AMBIENT_REACTIONS_MAX_PER_CHAT_PER_HOUR",
    "AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY",
    "GEMINI_EMBEDDING_RPD_LIMIT",
)


@pytest.mark.parametrize("env_name", ["dev", "prod"])
def test_retired_resources_permissions_and_overrides_cannot_return(monkeypatch, env_name):
    for key in _RETIRED_ENV_KEYS:
        monkeypatch.setenv(key, "true")
    monkeypatch.setenv("VECTOR_MEMORY_PROVIDER", "s3_vectors")
    monkeypatch.setenv("VECTOR_MEMORY_DIMENSIONS", "768")
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    template = _template(monkeypatch, env_name=env_name)
    rendered = json.dumps(template.to_json())
    for retired in (
        "bot-memory-",
        "vector-indexer",
        "vector-memory-tasks",
        "MemoryVector",
        "s3vectors:",
        "gemini-embedding-api-key",
    ):
        assert retired not in rendered
    assert not template.find_resources("AWS::S3Vectors::VectorBucket")
    assert not template.find_resources("AWS::S3Vectors::Index")
    assert len(template.find_resources("AWS::DynamoDB::Table")) == 3
    for resource in template.find_resources("AWS::Lambda::Function").values():
        assert not set(_RETIRED_ENV_KEYS).intersection(resource["Properties"]["Environment"]["Variables"])
    for filename in ("deploy.yml", "pr_check.yml"):
        assert not set(_RETIRED_ENV_KEYS).intersection(_workflow_variables(filename))
    example = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", Path(".env.example").read_text(), re.MULTILINE))
    assert not set(_RETIRED_ENV_KEYS).intersection(example)
    from services.memory_v2.models import RAW_RETENTION_SECONDS

    assert RAW_RETENTION_SECONDS == 30 * 86400
