"""CloudWatch alarms for Lambdas and SQS DLQs (no SNS wiring — alarms visible in console)."""

from __future__ import annotations

from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_sqs as sqs
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
from constructs import Construct


def add_lambda_operational_alarms(
    scope: Construct,
    *,
    env_name: str,
    logical_slug: str,
    fn: _lambda.IFunction,
    duration_p95_threshold_ms: int,
) -> None:
    """Errors, throttles, and duration p95 for a single Lambda function."""
    base = f"{CONSTRUCT_PREFIX}{logical_slug}"
    alarm_name_prefix = f"{RESOURCE_PREFIX}-{logical_slug}-{env_name}"

    cloudwatch.Alarm(
        scope,
        f"{base}ErrorsAlarm",
        alarm_name=f"{alarm_name_prefix}-errors",
        alarm_description=f"Lambda Errors >= 1 ({logical_slug}, {env_name})",
        metric=fn.metric_errors(),
        threshold=1,
        evaluation_periods=1,
        datapoints_to_alarm=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )

    cloudwatch.Alarm(
        scope,
        f"{base}ThrottlesAlarm",
        alarm_name=f"{alarm_name_prefix}-throttles",
        alarm_description=f"Lambda Throttles >= 1 ({logical_slug}, {env_name})",
        metric=fn.metric_throttles(),
        threshold=1,
        evaluation_periods=1,
        datapoints_to_alarm=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )

    cloudwatch.Alarm(
        scope,
        f"{base}DurationP95Alarm",
        alarm_name=f"{alarm_name_prefix}-duration-p95",
        alarm_description=(
            f"Lambda Duration p95 > {duration_p95_threshold_ms}ms ({logical_slug}, {env_name}); tune after profiling"
        ),
        metric=fn.metric_duration(statistic="p95"),
        threshold=float(duration_p95_threshold_ms),
        evaluation_periods=3,
        datapoints_to_alarm=2,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )


def add_sqs_dlq_visible_alarm(
    scope: Construct,
    *,
    env_name: str,
    logical_slug: str,
    dlq: sqs.IQueue,
) -> None:
    """Alert when poison messages land on the DLQ (visible count >= 1)."""
    base = f"{CONSTRUCT_PREFIX}{logical_slug}Dlq"
    alarm_name = f"{RESOURCE_PREFIX}-{logical_slug}-dlq-visible-{env_name}"

    cloudwatch.Alarm(
        scope,
        f"{base}VisibleAlarm",
        alarm_name=alarm_name,
        alarm_description=f"SQS DLQ has visible messages ({logical_slug}, {env_name})",
        metric=dlq.metric_approximate_number_of_messages_visible(),
        threshold=1,
        evaluation_periods=1,
        datapoints_to_alarm=1,
        comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
    )
