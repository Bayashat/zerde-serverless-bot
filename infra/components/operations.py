"""Private operational notifications, independently executable from the bot."""

import json

from aws_cdk import Duration, RemovalPolicy, Stack, Tags, Token
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cloudwatch_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from components.observability import add_sqs_dlq_visible_alarm
from constructs import Construct


class OperationsConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        is_prod: bool,
        runtime_active: bool,
        shared_layer: lambda_.ILayer,
        stats_table: dynamodb.ITable,
        admin_user_id: str,
        ssm_secret_prefix: str,
    ):
        super().__init__(scope, construct_id)
        self.runtime_active = runtime_active
        self.alarm_names: list[str] = []
        policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        stack = Stack.of(self)
        Tags.of(self).add("Component", "operations")
        self.topic = sns.Topic(self, "Topic", topic_name=f"{RESOURCE_PREFIX}-operations-{env_name}")
        self.topic.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.ServicePrincipal("cloudwatch.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[self.topic.topic_arn],
                conditions={
                    "StringEquals": {"aws:SourceAccount": stack.account},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:{stack.partition}:cloudwatch:{stack.region}:{stack.account}:"
                            f"alarm:{RESOURCE_PREFIX}-*{env_name}*"
                        )
                    },
                },
            )
        )
        # Subscription delivery and Lambda execution fail at different stages.
        self.subscription_dlq = sqs.Queue(
            self,
            "SubscriptionDlq",
            queue_name=f"{RESOURCE_PREFIX}-operations-delivery-dlq-{env_name}",
            retention_period=Duration.days(14),
            removal_policy=policy,
            enforce_ssl=True,
        )
        self.execution_dlq = sqs.Queue(
            self,
            "ExecutionDlq",
            queue_name=f"{RESOURCE_PREFIX}-operations-execution-dlq-{env_name}",
            retention_period=Duration.days(14),
            removal_policy=policy,
            enforce_ssl=True,
        )
        self.handler_lambda = PythonFunction(
            self,
            "Notifier",
            function_name=f"{RESOURCE_PREFIX}-operations-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "operations"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=lambda_.Architecture.ARM_64,
            layers=[shared_layer],
            timeout=Duration.seconds(60),
            memory_size=128,
            reserved_concurrent_executions=2 if runtime_active else 0,
            dead_letter_queue=self.execution_dlq,
            retry_attempts=2,
            max_event_age=Duration.hours(6),
            log_group=logs.LogGroup(
                self,
                "LogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-operations-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=policy,
            ),
            environment={
                "ENVIRONMENT": env_name,
                "OPERATIONS_TOPIC_ARN": self.topic.topic_arn,
                "OPERATIONS_ACCOUNT_ID": stack.account,
                "OPERATIONS_ALARM_NAMES": "[]",
                "ADMIN_USER_ID": admin_user_id,
                "SSM_SECRET_PREFIX": ssm_secret_prefix,
                "STATS_TABLE_NAME": stats_table.table_name,
            },
        )
        self.topic.add_subscription(
            subscriptions.LambdaSubscription(
                self.handler_lambda,
                dead_letter_queue=self.subscription_dlq,
            )
        )
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem"],
                resources=[stats_table.table_arn],
                conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["operations#*"]}},
            )
        )
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameters"],
                resources=[
                    f"arn:{stack.partition}:ssm:{stack.region}:{stack.account}:parameter{ssm_secret_prefix}/bot-token"
                ],
            )
        )
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["kms:Decrypt"],
                resources=["*"],
                conditions={
                    "StringEquals": {
                        "kms:ViaService": f"ssm.{stack.region}.amazonaws.com",
                        "kms:CallerAccount": stack.account,
                    }
                },
            )
        )
        if runtime_active:
            # Three extra alarms; avoid a full second set of duration/throttle alarms.
            self.register(
                cloudwatch.Alarm(
                    self,
                    "ErrorsAlarm",
                    alarm_name=f"{RESOURCE_PREFIX}-operations-errors-{env_name}",
                    metric=self.handler_lambda.metric_errors(),
                    threshold=1,
                    evaluation_periods=1,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                )
            )
            for slug, queue in (
                ("operations-delivery", self.subscription_dlq),
                ("operations-execution", self.execution_dlq),
            ):
                self.register(
                    add_sqs_dlq_visible_alarm(
                        self,
                        env_name=env_name,
                        logical_slug=slug,
                        dlq=queue,
                    )
                )

    def register(self, alarm: cloudwatch.Alarm) -> None:
        """Z06 can register a worker/backlog alarm without a second notification path."""
        if not self.runtime_active:
            raise ValueError("Do not create operational alarms for an inactive runtime")
        alarm.add_alarm_action(cloudwatch_actions.SnsAction(self.topic))
        alarm.add_ok_action(cloudwatch_actions.SnsAction(self.topic))
        # alarm.alarm_name is a Ref even with an explicit name. Using it in this
        # notifier's env would create a notifier -> own alarm -> notifier cycle.
        name = alarm.node.default_child.alarm_name
        if not name or Token.is_unresolved(name):
            raise ValueError("Registered operational alarms require an explicit stable name")
        self.alarm_names.append(name)
        self.handler_lambda.add_environment("OPERATIONS_ALARM_NAMES", json.dumps(self.alarm_names))

    def grant_budget_publish(self, grantee: iam.IGrantable) -> None:
        """Z08 remains the only budget owner; it publishes the documented typed event."""
        self.topic.grant_publish(grantee)
