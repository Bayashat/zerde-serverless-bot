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


def test_vector_policies_allow_metadata_query_dependencies() -> None:
    source = Path("infra/components/bot.py").read_text()
    vector_indexer_source = Path("infra/components/vector_indexer.py").read_text()

    assert '"s3vectors:QueryVectors"' in source
    assert '"s3vectors:GetVectors"' in source
    assert '"s3vectors:QueryVectors"' in vector_indexer_source
    assert '"s3vectors:GetVectors"' in vector_indexer_source


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
    template = _dev_template(monkeypatch)
    _, bot_lambda = _find_resource_by_property(
        template,
        "AWS::Lambda::Function",
        "FunctionName",
        "zerde-serverless-bot-dev",
    )

    env_vars = bot_lambda["Properties"]["Environment"]["Variables"]
    assert env_vars["GROUP_MEMORY_EXTRACTOR_PROVIDER"] == "gemini"
    assert env_vars["GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE"] == "0.65"


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
