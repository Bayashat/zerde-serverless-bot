import sys
from pathlib import Path
from typing import Any

from aws_cdk import App
from aws_cdk import aws_lambda as lambda_
from aws_cdk.assertions import Template

INFRA_DIR = Path("infra").resolve()
if str(INFRA_DIR) not in sys.path:
    sys.path.insert(0, str(INFRA_DIR))

from components import bot as bot_component  # noqa: E402
from components import news as news_component  # noqa: E402
from components import quiz as quiz_component  # noqa: E402
from components import vector_indexer as vector_indexer_component  # noqa: E402
from stack import ZerdeTelegramBotStack  # noqa: E402


def _stub_python_function(scope: Any, construct_id: str, **kwargs: Any) -> lambda_.Function:
    function_kwargs = {
        "architecture": kwargs.get("architecture"),
        "environment": kwargs.get("environment"),
        "function_name": kwargs.get("function_name"),
        "layers": kwargs.get("layers"),
        "memory_size": kwargs.get("memory_size"),
        "runtime": kwargs["runtime"],
        "timeout": kwargs.get("timeout"),
    }
    return lambda_.Function(
        scope,
        construct_id,
        handler="index.handler",
        code=lambda_.Code.from_inline("def handler(event, context):\n    return None\n"),
        **{key: value for key, value in function_kwargs.items() if value is not None},
    )


def _dev_template(monkeypatch: Any) -> Template:
    monkeypatch.setattr(bot_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(news_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(quiz_component, "PythonFunction", _stub_python_function)
    monkeypatch.setattr(vector_indexer_component, "PythonFunction", _stub_python_function)

    app = App()
    stack = ZerdeTelegramBotStack(app, "TestStack", env_name="dev")
    return Template.from_stack(stack)


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
    assert env_vars["DEEPSEEK_API_BASE"] == "https://api.deepseek.com"
    assert env_vars["DEEPSEEK_MODEL"] == "deepseek-chat"
    assert env_vars["MULTIMODAL_ENABLED"] == "true"
    assert env_vars["MULTIMODAL_MAX_DOWNLOAD_BYTES"] == "12000000"
    assert env_vars["MULTIMODAL_INLINE_MAX_BYTES"] == "8000000"
    assert env_vars["MULTIMODAL_TEXT_FILE_MAX_CHARS"] == "20000"


def test_broad_memory_type_retention_envs_fallback_to_legacy_retention(monkeypatch: Any) -> None:
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
    assert env_vars["GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS"] == "42"
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
