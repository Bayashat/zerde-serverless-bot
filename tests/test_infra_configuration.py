import sys
from pathlib import Path

from aws_cdk import App
from aws_cdk.assertions import Template

INFRA_DIR = Path("infra").resolve()
if str(INFRA_DIR) not in sys.path:
    sys.path.insert(0, str(INFRA_DIR))

from stack import ZerdeTelegramBotStack  # noqa: E402


def _dev_template() -> Template:
    app = App()
    stack = ZerdeTelegramBotStack(app, "TestStack", env_name="dev")
    return Template.from_stack(stack)


def test_bot_lambda_vector_policy_allows_metadata_query_dependencies() -> None:
    source = Path("infra/components/bot.py").read_text()

    assert '"s3vectors:QueryVectors"' in source
    assert '"s3vectors:GetVectors"' in source


def test_synthesizes_main_and_vector_dlq_visible_alarms() -> None:
    template = _dev_template()

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
