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

    app = App()
    stack = ZerdeTelegramBotStack(app, "TestStack", env_name="dev")
    return Template.from_stack(stack)


def test_bot_lambda_vector_policy_allows_metadata_query_dependencies() -> None:
    source = Path("infra/components/bot.py").read_text()

    assert '"s3vectors:QueryVectors"' in source
    assert '"s3vectors:GetVectors"' in source


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
