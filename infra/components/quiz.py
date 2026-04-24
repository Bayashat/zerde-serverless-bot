# infra/components/quiz.py
from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct

# Language → list of (hour_utc, minute_utc) trigger times for weekday quiz (Mon–Fri UTC)
_LANG_SCHEDULE: dict[str, list[tuple[int, int]]] = {
    "kk": [(8, 0)],  # 08:00 UTC = 13:00 Almaty
    "zh": [(8, 2)],  # 08:02 UTC
    "ru": [(8, 4)],  # 08:04 UTC
}

# Language → (hour_utc, minute_utc) for Sunday evening leaderboard
_LEADERBOARD_SCHEDULE: dict[str, tuple[int, int]] = {
    "kk": (13, 0),  # 13:00 UTC = 18:00 Almaty
    "zh": (13, 0),  # 13:00 UTC
    "ru": (13, 0),  # 13:00 UTC
}


class QuizConstruct(Construct):
    """Daily Quiz: Quiz Lambda + DynamoDB table + EventBridge schedules (prod-only).

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
        log_level: str,
        telegram_api_base: str,
        ai_provider: str,
        quiz_gemini_model: str,
        ssm_secret_prefix: str,
        groq_api_base: str,
        groq_model: str,
        quiz_llm_rpd: str,
        chats: dict[str, list[str]],
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
            architecture=_lambda.Architecture.X86_64,
            timeout=Duration.seconds(60),
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
                "SSM_SECRET_PREFIX": ssm_secret_prefix,
                "TELEGRAM_API_BASE": telegram_api_base,
                "AI_PROVIDER": ai_provider,
                "QUIZ_GEMINI_MODEL": quiz_gemini_model,
                "TABLE_NAME": self.quiz_table.table_name,
                "QUIZ_LLM_RPD": quiz_llm_rpd,
                "GROQ_API_BASE": groq_api_base,
                "GROQ_MODEL": groq_model,
            },
        )

        stack = Stack.of(self)
        quiz_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="ReadZerdeSSMSecrets",
                actions=["ssm:GetParameters"],
                resources=[f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{ssm_secret_prefix}/*"],
            )
        )
        quiz_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="DecryptZerdeSSMSecrets",
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

        self.quiz_lambda = quiz_lambda
        self.quiz_table.grant_read_write_data(quiz_lambda)

        # ── EventBridge (prod-only) ────────────────────────────────────────
        if is_prod:
            for lang, schedules in _LANG_SCHEDULE.items():
                chat_ids = chats.get(lang, [])
                if not chat_ids:
                    continue
                for hour_utc, minute_utc in schedules:
                    slot = f"{hour_utc:02d}{minute_utc:02d}"
                    rule = events.Rule(
                        self,
                        f"{CONSTRUCT_PREFIX}QuizRule{lang.upper()}{slot}",
                        rule_name=f"{RESOURCE_PREFIX}-quiz-{lang}-{slot}-{env_name}",
                        description=(
                            f"Trigger quiz lambda Mon–Fri at {hour_utc:02d}:{minute_utc:02d} UTC " f"for {lang} chats"
                        ),
                        schedule=events.Schedule.cron(
                            minute=str(minute_utc),
                            hour=str(hour_utc),
                            month="*",
                            week_day="MON-FRI",
                            year="*",
                        ),
                    )
                    rule.add_target(
                        events_targets.LambdaFunction(
                            quiz_lambda,
                            event=events.RuleTargetInput.from_object(
                                {
                                    "chat_ids": chat_ids,
                                    "lang": lang,
                                }
                            ),
                        )
                    )

            # Friday leaderboard (18:00 Almaty = 13:00 UTC, day-of-week=5 in cron = Friday)
            for lang, (hour_utc, minute_utc) in _LEADERBOARD_SCHEDULE.items():
                chat_ids = chats.get(lang, [])
                if not chat_ids:
                    continue
                slot = f"{hour_utc:02d}{minute_utc:02d}"
                lb_rule = events.Rule(
                    self,
                    f"{CONSTRUCT_PREFIX}LeaderboardRule{lang.upper()}{slot}",
                    rule_name=f"{RESOURCE_PREFIX}-leaderboard-{lang}-{slot}-{env_name}",
                    description=f"Send weekly leaderboard at {hour_utc:02d}:{minute_utc:02d} UTC on Sundays for {lang}",
                    schedule=events.Schedule.cron(
                        minute=str(minute_utc),
                        hour=str(hour_utc),
                        week_day="FRI",
                        month="*",
                        year="*",
                    ),
                )
                lb_rule.add_target(
                    events_targets.LambdaFunction(
                        quiz_lambda,
                        event=events.RuleTargetInput.from_object(
                            {
                                "chat_ids": chat_ids,
                                "lang": lang,
                                "action": "leaderboard",
                            }
                        ),
                    )
                )
