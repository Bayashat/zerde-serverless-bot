"""Compact shared inventory and one hourly monitor in the existing Bot Lambda."""

from aws_cdk import Duration, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda_destinations as destinations
from constructs import Construct


class MemoryCostConstruct(Construct):
    def __init__(self, scope, construct_id, *, bot_function, worker_function, main_dlq, env_name, metering_started_at):
        super().__init__(scope, construct_id)
        if type(metering_started_at) is not int or metering_started_at < 0:
            raise ValueError("MEMORY_COST_METERING_STARTED_AT must be a nonnegative UTC timestamp")
        stack = Stack.of(self)
        declaration = stack.to_json_string(
            {
                "schema": 1,
                "region": stack.region,
                "account_id": stack.account,
                "metering_started_at": metering_started_at,
                "alarm_count": 10,
            }
        )
        for function in (bot_function, worker_function):
            function.add_environment("MEMORY_COST_INVENTORY", declaration)
            function.add_environment("MEMORY_COST_INSTRUMENTATION_SCHEMA", "1")
        if env_name != "prod":
            return
        prefix = f"arn:{stack.partition}:"
        scope = f"{stack.region}:{stack.account}"
        function_arns = [
            prefix + f"lambda:{scope}:function:zerde-serverless-{kind}-{env}"
            for env in ("dev", "prod")
            for kind in ("bot", "memory-v2-worker")
        ]
        table_arns = [prefix + f"dynamodb:{scope}:table/zerde-serverless-memory-v2-{env}" for env in ("dev", "prod")]
        queue_arns = [
            prefix + f"sqs:{scope}:zerde-serverless-memory-v2-{kind}-{env}"
            for env in ("dev", "prod")
            for kind in ("queue", "dlq")
        ]
        log_arns = [
            prefix + f"logs:{scope}:log-group:/aws/lambda/zerde-serverless-{kind}-{env}:*"
            for env in ("dev", "prod")
            for kind in ("bot", "memory-v2-worker")
        ]
        for actions, resources in (
            (["lambda:GetFunctionConfiguration", "lambda:ListProvisionedConcurrencyConfigs"], function_arns),
            (["dynamodb:DescribeTable", "dynamodb:DescribeContinuousBackups"], table_arns),
            (["sqs:GetQueueAttributes"], queue_arns),
            (["logs:StartQuery"], log_arns),
            (["cloudwatch:GetMetricData", "logs:DescribeLogGroups", "logs:GetQueryResults", "logs:StopQuery"], ["*"]),
        ):
            bot_function.add_to_role_policy(iam.PolicyStatement(actions=actions, resources=resources))
        # All budget keys remain in prod. No cross-environment personal Query permission.
        bot_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Query", "dynamodb:DeleteItem"],
                resources=[table_arns[1]],
                conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["MEMORY_BUDGET#*"]}},
            )
        )
        self.rule = events.Rule(
            self, "Hourly", schedule=events.Schedule.rate(Duration.hours(1)), enabled=metering_started_at > 0
        )
        self.rule.add_target(
            targets.LambdaFunction(
                bot_function,
                event=events.RuleTargetInput.from_object({"schema": 2, "task_type": "MONITOR_MEMORY_V2_COST"}),
                retry_attempts=0,
                max_event_age=Duration.minutes(15),
                dead_letter_queue=main_dlq,
            )
        )
        bot_function.configure_async_invoke(
            max_event_age=Duration.minutes(15), retry_attempts=0, on_failure=destinations.SqsDestination(main_dlq)
        )
