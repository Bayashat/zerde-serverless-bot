"""One bounded memory queue/worker and recovery entrypoint, isolated from bot tasks."""

from aws_cdk import Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as event_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_events
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import LAMBDA_BUNDLING, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from components.observability import add_lambda_operational_alarms, add_sqs_age_alarm, add_sqs_dlq_visible_alarm
from constructs import Construct

# Imported core config still serves the bot bundle; keep the inherited values
# from its sole CDK configuration owner instead of inventing worker defaults.
_CONFIG_KEYS = {
    "ADMIN_USER_ID",
    "CHAT_LANG_MAP",
    "GEMINI_RPD_LIMIT",
    "CAPTCHA_TIMEOUT_SECONDS",
    "KICK_BAN_DURATION_SECONDS",
    "CAPTCHA_MAX_ATTEMPTS",
    "VOTEBAN_THRESHOLD",
    "VOTEBAN_FORGIVE_THRESHOLD",
    "LOG_LEVEL",
    "SSM_SECRET_PREFIX",
}


def grant_project_budget(grantee, table):
    table_arn = table.table_arn
    grantee.add_to_role_policy(
        iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"],
            resources=[table_arn],
            conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["MEMORY_BUDGET#*", "MEMORY_ATTEMPT#*"]}},
        )
    )


class MemoryWorkerConstruct(Construct):
    def __init__(
        self,
        scope,
        construct_id,
        *,
        env_name,
        is_prod,
        runtime_active,
        shared_layer,
        memory_table,
        stats_table,
        bot_environment,
        operations,
    ):
        super().__init__(scope, construct_id)
        Tags.of(self).add("Component", "memory-v2")
        stack = Stack.of(self)
        policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        self.dlq = sqs.Queue(
            self,
            "Dlq",
            queue_name=f"{RESOURCE_PREFIX}-memory-v2-dlq-{env_name}",
            retention_period=Duration.days(14),
            enforce_ssl=True,
            removal_policy=policy,
        )
        self.queue = sqs.Queue(
            self,
            "Queue",
            queue_name=f"{RESOURCE_PREFIX}-memory-v2-queue-{env_name}",
            visibility_timeout=Duration.seconds(740),
            retention_period=Duration.days(1),
            receive_message_wait_time=Duration.seconds(20),
            enforce_ssl=True,
            dead_letter_queue=sqs.DeadLetterQueue(queue=self.dlq, max_receive_count=5),
            removal_policy=policy,
        )
        self.budget_table = (
            memory_table
            if is_prod
            else dynamodb.Table.from_table_name(self, "ProjectBudgetTable", f"{RESOURCE_PREFIX}-memory-v2-prod")
        )
        environment = {key: value for key, value in bot_environment.items() if key in _CONFIG_KEYS}
        environment.update(
            {
                "ENVIRONMENT": env_name,
                "STATS_TABLE_NAME": stats_table.table_name,
                "QUEUE_URL": self.queue.queue_url,
                "MEMORY_V2_QUEUE_URL": self.queue.queue_url,
                "MEMORY_V2_TABLE_NAME": memory_table.table_name,
                "MEMORY_BUDGET_TABLE_NAME": self.budget_table.table_name,
                "GEMINI_MODEL": "gemini-3.1-flash-lite",
                "OPERATIONS_TOPIC_ARN": operations.topic.topic_arn,
            }
        )
        self.handler_lambda = PythonFunction(
            self,
            "Worker",
            function_name=f"{RESOURCE_PREFIX}-memory-v2-worker-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="memory_worker_main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            bundling=LAMBDA_BUNDLING,
            architecture=lambda_.Architecture.ARM_64,
            layers=[shared_layer],
            memory_size=512,
            timeout=Duration.seconds(120),
            reserved_concurrent_executions=2 if runtime_active else 0,
            environment=environment,
            dead_letter_queue=self.dlq,
            retry_attempts=2,
            max_event_age=Duration.hours(1),
            log_group=logs.LogGroup(
                self,
                "LogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-memory-v2-worker-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=policy,
            ),
        )
        memory_table.grant_read_write_data(self.handler_lambda)
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"],
                resources=[stats_table.table_arn],
                conditions={"ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["spam_case#*", "RATE#*"]}},
            )
        )
        # Recovery scans only approval metadata with a fixed projection; no source
        # body is recovered from the stats table. Scan has no LeadingKeys support.
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["dynamodb:Scan"],
                resources=[stats_table.table_arn],
            )
        )
        grant_project_budget(self.handler_lambda, self.budget_table)
        self.queue.grant_send_messages(self.handler_lambda)
        self.handler_lambda.add_event_source(
            lambda_events.SqsEventSource(
                self.queue,
                batch_size=20,
                max_batching_window=Duration.seconds(20),
                max_concurrency=2,
                report_batch_item_failures=True,
                enabled=runtime_active,
            )
        )
        self.recovery = events.Rule(
            self,
            "Recovery",
            rule_name=f"{RESOURCE_PREFIX}-memory-v2-recovery-{env_name}",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            enabled=runtime_active,
        )
        self.recovery.add_target(
            event_targets.LambdaFunction(
                self.handler_lambda,
                event=events.RuleTargetInput.from_object({"schema": 2, "task_type": "RECOVER_MEMORY_V2"}),
                dead_letter_queue=self.dlq,
                retry_attempts=2,
                max_event_age=Duration.hours(1),
            )
        )
        prefix = bot_environment["SSM_SECRET_PREFIX"]
        self.handler_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameters"],
                resources=[
                    f"arn:{stack.partition}:ssm:{stack.region}:{stack.account}:parameter{prefix}/gemini-api-key"
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
        operations.grant_budget_publish(self.handler_lambda)
        if runtime_active:
            for alarm in add_lambda_operational_alarms(
                self,
                env_name=env_name,
                logical_slug="memory-v2-worker",
                fn=self.handler_lambda,
                duration_p95_threshold_ms=100_000,
            ):
                operations.register(alarm)
            operations.register(
                add_sqs_dlq_visible_alarm(self, env_name=env_name, logical_slug="memory-v2", dlq=self.dlq)
            )
            operations.register(
                add_sqs_age_alarm(
                    self, env_name=env_name, logical_slug="memory-v2", queue=self.queue, threshold_seconds=300
                )
            )
