from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class QuizConstruct(Construct):
    """Daily Quiz: Quiz Lambda + DynamoDB table + EventBridge schedule (prod-only).

    Exposes:
        quiz_table (dynamodb.Table): Quiz DynamoDB table for cross-construct access.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        is_prod: bool,
        bot_token: str,
        quizapi_key: str,
        quiz_chats: list[str],
        log_level: str,
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        # ── DynamoDB Table ─────────────────────────────────────────────────
        self.quiz_table = dynamodb.Table(
            self,
            f"{CONSTRUCT_PREFIX}QuizTable",
            table_name=f"{RESOURCE_PREFIX}-quiz-{env_name}",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
            deletion_protection=is_prod,
            time_to_live_attribute="ttl",
        )

        self.quiz_table.add_global_secondary_index(
            index_name="PollIdIndex",
            partition_key=dynamodb.Attribute(name="poll_id", type=dynamodb.AttributeType.STRING),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # ── Quiz Lambda ────────────────────────────────────────────────────
        quiz_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}QuizLambda",
            function_name=f"{RESOURCE_PREFIX}-quiz-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "quiz"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.seconds(30),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}QuizLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-quiz-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment={
                "LOG_LEVEL": log_level,
                "BOT_TOKEN": bot_token,
                "QUIZAPI_KEY": quizapi_key,
                "QUIZ_TABLE_NAME": self.quiz_table.table_name,
            },
        )

        self.quiz_table.grant_read_write_data(quiz_lambda)

        # ── EventBridge (prod-only) ────────────────────────────────────────
        if is_prod and quiz_chats:
            rule = events.Rule(
                self,
                f"{CONSTRUCT_PREFIX}QuizRule",
                rule_name=f"{RESOURCE_PREFIX}-quiz-daily-{env_name}",
                description="Trigger quiz lambda daily at 03:00 UTC (08:00 Almaty)",
                schedule=events.Schedule.cron(
                    minute="0",
                    hour="3",
                    day="*",
                    month="*",
                    year="*",
                ),
            )
            rule.add_target(
                events_targets.LambdaFunction(
                    quiz_lambda,
                    event=events.RuleTargetInput.from_object({"chat_ids": quiz_chats}),
                )
            )
