import json
import re
import runpy
import sys
from pathlib import Path
from typing import Any

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
from components import vector_indexer as vector_indexer_component  # noqa: E402
from stack import ZerdeTelegramBotStack  # noqa: E402

_CONFIG_DEFAULTS = {
    "MAIN_TASK_QUEUE_RETENTION_DAYS": "1",
    "MAIN_TASK_DLQ_RETENTION_DAYS": "14",
    "VECTOR_MEMORY_QUEUE_RETENTION_DAYS": "4",
    "VECTOR_MEMORY_DLQ_RETENTION_DAYS": "14",
    "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS": "30",
    "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS": "7",
    "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS": "3650",
    "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS": "3650",
    "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS": "3",
    "GROUP_MEMORY_EXTRACTOR_PROVIDER": "gemini",
    "GROUP_MEMORY_EXTRACTOR_MODE": "gemini_candidate_only",
    "GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE": "0.65",
    "GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT": "50",
    "GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT": "20",
    "AGENT_BOT_ID": "",
    "AGENT_PROACTIVE_DELAY_SECONDS": "45",
    "MULTIMODAL_ENABLED": "true",
    "MULTIMODAL_MAX_DOWNLOAD_BYTES": "12000000",
    "MULTIMODAL_INLINE_MAX_BYTES": "8000000",
    "MULTIMODAL_TEXT_FILE_MAX_CHARS": "20000",
    "VECTOR_MEMORY_SCHEMA_VERSION": "1",
    "GROUP_MEMORY_RECENT_LIMIT": "300",
    "AGENT_RECENT_CONTEXT_LIMIT": "100",
    "AGENT_DAILY_PROACTIVE_LIMIT": "3",
    "VECTOR_MEMORY_INDEX_THROTTLE_SECONDS": "3",
}
_QUEUE_CONFIG_KEYS = {
    "MAIN_TASK_QUEUE_RETENTION_DAYS",
    "MAIN_TASK_DLQ_RETENTION_DAYS",
    "VECTOR_MEMORY_QUEUE_RETENTION_DAYS",
    "VECTOR_MEMORY_DLQ_RETENTION_DAYS",
}


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
        if key in {"GROUP_MEMORY_LONG_TERM_RETENTION_DAYS", "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS"}:
            fallback = " || vars.GROUP_MEMORY_RETENTION_DAYS" + fallback
        assert deploy[key] == "${{ vars." + key + fallback + " }}"
    for unused in ("AI_PROVIDER", "WTF_GEMINI_MODEL", "FALLBACK_MODEL"):
        assert unused not in deploy


def test_config_defaults_agree_between_example_runtime_and_lambda_template(monkeypatch: Any) -> None:
    for key in _CONFIG_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    # Reproduce the deployed legacy value that previously forced raw retention to ten years.
    monkeypatch.setenv("GROUP_MEMORY_RETENTION_DAYS", "3650")
    runtime = runpy.run_path("src/bot/core/config.py")
    example = dict(re.findall(r"^([A-Z][A-Z0-9_]+)=(.*)$", Path(".env.example").read_text(), re.MULTILINE))
    template = _dev_template(monkeypatch)
    _, bot = _find_resource_by_property(template, "AWS::Lambda::Function", "FunctionName", "zerde-serverless-bot-dev")
    deployed = bot["Properties"]["Environment"]["Variables"]
    for key, expected in _CONFIG_DEFAULTS.items():
        assert example[key] == expected, key
        if key not in _QUEUE_CONFIG_KEYS:
            assert deployed[key] == expected, key
            assert _runtime_value_as_text(runtime[key]) == expected, key


def test_typed_config_overrides_reach_bot_runtime_and_indexer(monkeypatch: Any) -> None:
    overrides = {
        "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS": "11",
        "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS": "5",
        "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS": "180",
        "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS": "90",
        "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS": "2",
        "GROUP_MEMORY_EXTRACTOR_PROVIDER": "rules",
        "GROUP_MEMORY_EXTRACTOR_MODE": "off",
        "GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE": "0.91",
        "GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT": "17",
        "GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT": "8",
        "AGENT_BOT_ID": "12345",
        "AGENT_PROACTIVE_DELAY_SECONDS": "62",
        "MULTIMODAL_ENABLED": "false",
        "MULTIMODAL_MAX_DOWNLOAD_BYTES": "9000000",
        "MULTIMODAL_INLINE_MAX_BYTES": "6000000",
        "MULTIMODAL_TEXT_FILE_MAX_CHARS": "15000",
        "VECTOR_MEMORY_SCHEMA_VERSION": "2",
    }
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    runtime = runpy.run_path("src/bot/core/config.py")
    template = _dev_template(monkeypatch)
    for name in ("zerde-serverless-bot-dev", "zerde-serverless-vector-indexer-dev"):
        _, function = _find_resource_by_property(template, "AWS::Lambda::Function", "FunctionName", name)
        deployed = function["Properties"]["Environment"]["Variables"]
        for key, expected in overrides.items():
            assert deployed[key] == expected, (name, key)
            assert _runtime_value_as_text(runtime[key]) == expected, key


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


def _template(monkeypatch: Any, *, env_name: str) -> Template:
    monkeypatch.setattr(memory_worker_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(operations_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(bot_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(news_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(quiz_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(vector_indexer_component, "PythonFunction", _stub_python_function)

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


def test_s3_vectors_permissions_are_scoped_by_lambda_role(monkeypatch: Any) -> None:
    monkeypatch.setenv("VECTOR_MEMORY_ENABLED", "true")
    monkeypatch.setenv("VECTOR_MEMORY_PROVIDER", "s3_vectors")
    template = _dev_template(monkeypatch)
    _, bot_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )
    _, vector_indexer_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-vector-indexer-dev",
    )

    bot_actions = _role_actions_for_service(template, _function_role_id(bot_lambda), "s3vectors")
    vector_indexer_actions = _role_actions_for_service(
        template,
        _function_role_id(vector_indexer_lambda),
        "s3vectors",
    )

    assert {
        "s3vectors:QueryVectors",
        "s3vectors:GetVectors",
        "s3vectors:DeleteVectors",
        "s3vectors:GetIndex",
    }.issubset(bot_actions)
    assert "s3vectors:PutVectors" not in bot_actions
    assert "s3vectors:ListVectors" not in bot_actions
    assert {
        "s3vectors:PutVectors",
        "s3vectors:QueryVectors",
        "s3vectors:GetVectors",
        "s3vectors:DeleteVectors",
        "s3vectors:ListVectors",
        "s3vectors:GetIndex",
    }.issubset(vector_indexer_actions)


def test_main_and_vector_queues_have_separate_lambda_consumers(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)
    bot_lambda_id, _ = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )
    vector_indexer_lambda_id, _ = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-vector-indexer-dev",
    )
    main_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-queue-dev",
    )
    vector_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-queue-dev",
    )

    assert _event_source_targets(template, main_queue_id) == [{"Ref": bot_lambda_id}]
    assert _event_source_targets(template, vector_queue_id) == [{"Ref": vector_indexer_lambda_id}]


def test_prod_contest_recovery_schedule_exists_without_configured_chats(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)
    for key in (
        "CHATS_KK",
        "CHATS_ZH",
        "CHATS_RU",
        "NEWS_CHATS_KK",
        "NEWS_CHATS_ZH",
        "NEWS_CHATS_RU",
        "QUIZ_CHATS_KK",
        "QUIZ_CHATS_ZH",
        "QUIZ_CHATS_RU",
    ):
        monkeypatch.setenv(key, "")

    template = _template(monkeypatch, env_name="prod")
    rule_id, rule = _find_resource_by_property(
        template,
        "AWS::Events::Rule",
        "Name",
        "zerde-serverless-contest-ttl-recovery-prod",
    )
    queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-timeout-tasks-queue-prod",
    )

    properties = rule["Properties"]
    assert properties["ScheduleExpression"] == "cron(50 20 * * ? *)"
    assert json.loads(properties["Targets"][0]["Input"]) == {"task_type": "PROCESS_CONTEST_TTL_RECOVERY"}
    assert properties["Targets"][0]["Arn"] == {"Fn::GetAtt": [queue_id, "Arn"]}
    assert not any(
        resource.get("Type") == "AWS::Events::Rule"
        and resource.get("Properties", {}).get("Name") == "zerde-serverless-group-memory-daily-summary-prod"
        for resource in _resources(template).values()
    )

    expected_queue_arn = {"Fn::GetAtt": [queue_id, "Arn"]}
    expected_rule_arn = {"Fn::GetAtt": [rule_id, "Arn"]}
    statements = [
        statement
        for resource in _resources(template).values()
        if resource.get("Type") == "AWS::SQS::QueuePolicy"
        for statement in _as_list(resource["Properties"]["PolicyDocument"]["Statement"])
    ]
    assert any(
        statement.get("Principal") == {"Service": "events.amazonaws.com"}
        and "sqs:SendMessage" in _as_list(statement.get("Action", []))
        and statement.get("Resource") == expected_queue_arn
        and statement.get("Condition", {}).get("ArnEquals", {}).get("aws:SourceArn") == expected_rule_arn
        for statement in statements
    )


def test_dev_has_no_scheduled_contest_recovery(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)

    assert not any(
        resource.get("Type") == "AWS::Events::Rule"
        and resource.get("Properties", {}).get("Name") == "zerde-serverless-contest-ttl-recovery-dev"
        for resource in _resources(template).values()
    )


def test_sqs_queue_retention_defaults_are_operationally_safe(monkeypatch: Any) -> None:
    monkeypatch.setattr("stack.load_dotenv", lambda *args, **kwargs: None)
    for key in (
        "MAIN_TASK_QUEUE_RETENTION_DAYS",
        "MAIN_TASK_DLQ_RETENTION_DAYS",
        "VECTOR_MEMORY_QUEUE_RETENTION_DAYS",
        "VECTOR_MEMORY_DLQ_RETENTION_DAYS",
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
    _, vector_queue = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-queue-dev",
    )
    _, vector_dlq = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-dlq-dev",
    )

    assert main_queue["Properties"]["MessageRetentionPeriod"] == 86_400
    assert main_dlq["Properties"]["MessageRetentionPeriod"] == 1_209_600
    assert vector_queue["Properties"]["MessageRetentionPeriod"] == 345_600
    assert vector_dlq["Properties"]["MessageRetentionPeriod"] == 1_209_600


def test_sqs_queue_retention_is_configurable_from_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("MAIN_TASK_QUEUE_RETENTION_DAYS", "2")
    monkeypatch.setenv("MAIN_TASK_DLQ_RETENTION_DAYS", "3")
    monkeypatch.setenv("VECTOR_MEMORY_QUEUE_RETENTION_DAYS", "7")
    monkeypatch.setenv("VECTOR_MEMORY_DLQ_RETENTION_DAYS", "10")

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
    _, vector_queue = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-queue-dev",
    )
    _, vector_dlq = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-dlq-dev",
    )

    assert main_queue["Properties"]["MessageRetentionPeriod"] == 172_800
    assert main_dlq["Properties"]["MessageRetentionPeriod"] == 259_200
    assert vector_queue["Properties"]["MessageRetentionPeriod"] == 604_800
    assert vector_dlq["Properties"]["MessageRetentionPeriod"] == 864_000


def test_bot_can_send_but_not_consume_vector_queue(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)
    _, bot_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )
    vector_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-queue-dev",
    )
    bot_role_id = _function_role_id(bot_lambda)

    assert _role_has_action_on_queue(template, bot_role_id, {"sqs:SendMessage"}, vector_queue_id)
    assert not _role_has_action_on_queue(
        template,
        bot_role_id,
        {"sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"},
        vector_queue_id,
    )


def test_vector_indexer_consumes_vector_queue(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)
    _, vector_indexer_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-vector-indexer-dev",
    )
    vector_queue_id, _ = _find_resource_by_property(
        template,
        "AWS::SQS::Queue",
        "QueueName",
        "zerde-serverless-vector-memory-tasks-queue-dev",
    )
    vector_role_id = _function_role_id(vector_indexer_lambda)

    assert _role_has_action_on_queue(
        template,
        vector_role_id,
        {"sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility"},
        vector_queue_id,
    )
    assert _role_has_action_on_queue(template, vector_role_id, {"sqs:SendMessage"}, vector_queue_id)


def test_bot_environment_configures_memory_extractor(monkeypatch: Any) -> None:
    for key in (
        "GROUP_MEMORY_RETENTION_DAYS",
        "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS",
        "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS",
        "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS",
        "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS",
        "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS",
        "DEEPSEEK_API_BASE",
        "DEEPSEEK_MODEL",
        "GROQ_MODEL",
        "GROQ_SPAM_MODEL",
        "AGENT_PROACTIVE_DECISION_GROQ_MODELS",
        "AMBIENT_REACTIONS_DECISION_GROQ_MODELS",
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
    assert env_vars["GROUP_MEMORY_RETENTION_DAYS"] == "3650"
    assert env_vars["GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS"] == "30"
    assert env_vars["GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS"] == "7"
    assert env_vars["GROUP_MEMORY_LONG_TERM_RETENTION_DAYS"] == "3650"
    assert env_vars["GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS"] == "3650"
    assert env_vars["GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS"] == "3"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_PROVIDER"] == "gemini"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_MODE"] == "gemini_candidate_only"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE"] == "0.65"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT"] == "50"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT"] == "20"
    assert env_vars["AGENT_PROACTIVE_DELAY_SECONDS"] == "45"
    assert env_vars["AMBIENT_REACTIONS_ENABLED"] == "true"
    assert env_vars["AMBIENT_REACTIONS_SAMPLE_RATE"] == "0.80"
    assert env_vars["AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD"] == "0.80"
    assert env_vars["AMBIENT_REACTIONS_MIN_GAP_PER_CHAT_SECONDS"] == "60"
    assert env_vars["AMBIENT_REACTIONS_MIN_GAP_PER_USER_SECONDS"] == "300"
    assert env_vars["AMBIENT_REACTIONS_MAX_PER_CHAT_PER_HOUR"] == "12"
    assert env_vars["AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY"] == "100"
    assert env_vars["GROQ_MODEL"] == "openai/gpt-oss-120b"
    assert env_vars["GROQ_SPAM_MODEL"] == "openai/gpt-oss-safeguard-20b"
    assert env_vars["AGENT_PROACTIVE_DECISION_GROQ_MODELS"] == (
        "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b"
    )
    assert env_vars["AMBIENT_REACTIONS_DECISION_GROQ_MODELS"] == (
        "openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b"
    )
    assert env_vars["DEEPSEEK_API_BASE"] == "https://api.deepseek.com"
    assert env_vars["DEEPSEEK_MODEL"] == "deepseek-chat"
    assert env_vars["MULTIMODAL_ENABLED"] == "true"
    assert env_vars["MULTIMODAL_MAX_DOWNLOAD_BYTES"] == "12000000"
    assert env_vars["MULTIMODAL_INLINE_MAX_BYTES"] == "8000000"
    assert env_vars["MULTIMODAL_TEXT_FILE_MAX_CHARS"] == "20000"


def test_raw_retention_does_not_inherit_legacy_long_term_retention(monkeypatch: Any) -> None:
    monkeypatch.setenv("GROUP_MEMORY_RETENTION_DAYS", "42")
    for key in (
        "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS",
        "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS",
        "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS",
        "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS",
        "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS",
    ):
        monkeypatch.delenv(key, raising=False)

    template = _dev_template(monkeypatch)
    _, bot_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )

    env_vars = bot_lambda["Properties"]["Environment"]["Variables"]
    assert env_vars["GROUP_MEMORY_RETENTION_DAYS"] == "42"
    assert env_vars["GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS"] == "30"
    assert env_vars["GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS"] == "7"
    assert env_vars["GROUP_MEMORY_LONG_TERM_RETENTION_DAYS"] == "42"
    assert env_vars["GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS"] == "42"
    assert env_vars["GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS"] == "3"


def test_vector_indexer_ssm_access_is_limited_to_gemini(monkeypatch: Any) -> None:
    template = _dev_template(monkeypatch)
    _, vector_indexer_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-vector-indexer-dev",
    )
    vector_role_id = _function_role_id(vector_indexer_lambda)
    ssm_statements = [
        statement
        for statement in _role_statements(template, vector_role_id)
        if "ssm:GetParameters" in _as_list(statement.get("Action", []))
    ]
    serialized_statements = repr(ssm_statements)

    assert "gemini-api-key" in serialized_statements
    assert "gemini-embedding-api-key" in serialized_statements
    assert "bot-token" not in serialized_statements
    assert "webhook-secret-token" not in serialized_statements
    assert "groq-api-key" not in serialized_statements
    assert "deepseek-api-key" not in serialized_statements


def test_synthesizes_vector_indexer_operational_alarms(monkeypatch: Any) -> None:
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    template = _dev_template(monkeypatch)

    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "zerde-serverless-vector-indexer-dev-errors",
            "MetricName": "Errors",
            "Namespace": "AWS/Lambda",
            "Threshold": 1,
        },
    )


def test_synthesizes_main_and_vector_dlq_visible_alarms(monkeypatch: Any) -> None:
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
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "AlarmName": "zerde-serverless-vector-memory-tasks-dlq-visible-dev",
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
    assert len(functions) == 6
    assert all(fn["Properties"]["ReservedConcurrentExecutions"] == 0 for fn in functions.values())
    mappings = template.find_resources("AWS::Lambda::EventSourceMapping")
    assert len(mappings) == 3
    assert all(mapping["Properties"]["Enabled"] is False for mapping in mappings.values())
    assert not template.find_resources("AWS::CloudWatch::Alarm")


def test_active_runtime_registers_private_alarm_and_recovery_actions(monkeypatch):
    monkeypatch.setenv("DEV_RUNTIME_ENABLED", "true")
    template = _dev_template(monkeypatch)
    alarms = template.find_resources("AWS::CloudWatch::Alarm")
    assert len(alarms) == 22
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
    assert len(json.loads(variables["OPERATIONS_ALARM_NAMES"])) == 22
    assert notifier["Properties"]["Timeout"] == 60
    assert "DeadLetterConfig" in notifier["Properties"]
    subscription = next(iter(template.find_resources("AWS::SNS::Subscription").values()))
    assert "RedrivePolicy" in subscription["Properties"]
    statements = _role_statements(template, _function_role_id(notifier))
    ssm = [s for s in statements if "ssm:GetParameters" in _as_list(s.get("Action", []))]
    assert "bot-token" in repr(ssm) and "gemini-api-key" not in repr(ssm)
    ddb = [s for s in statements if "dynamodb:UpdateItem" in _as_list(s.get("Action", []))]
    assert ddb[0]["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] == ["operations#*"]


def test_prod_ignores_dev_idle_flag_preserves_vector_limit_and_enables_quiz_pitr(monkeypatch):
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
    ) == [2, 3, 10]
    assert len(template.find_resources("AWS::CloudWatch::Alarm")) == 22
    tags = {tag["Key"]: tag["Value"] for tag in quiz["Properties"]["Tags"]}
    assert tags == {"Project": "ZerdeBot", "Environment": "prod", "Component": "quiz"}
