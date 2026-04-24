from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct

# Language → list of (hour_utc, minute_utc) trigger times
_LANG_SCHEDULE: dict[str, list[tuple[int, int]]] = {
    "kk": [(4, 0)],  # 04:00 UTC
    "zh": [(4, 5)],  # 04:05 UTC
    "ru": [(4, 10)],  # 04:10 UTC
}


class NewsConstruct(Construct):
    """Daily IT news digest: News Lambda + EventBridge schedules (prod-only)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        is_prod: bool,
        ssm_secret_prefix: str,
        chats: dict[str, list[str]],
        ai_provider: str,
        news_gemini_model: str,
        news_fallback_model: str,
        log_level: str,
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        news_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}NewsLambda",
            function_name=f"{RESOURCE_PREFIX}-news-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "news"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.minutes(5),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}NewsLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-news-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment={
                "LOG_LEVEL": log_level,
                "SSM_SECRET_PREFIX": ssm_secret_prefix,
                "NEWS_AI_PROVIDER": ai_provider,
                "NEWS_GEMINI_MODEL": news_gemini_model,
                "NEWS_FALLBACK_MODEL": news_fallback_model,
            },
        )

        stack = Stack.of(self)
        news_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="ReadZerdeSSMSecrets",
                actions=["ssm:GetParameters"],
                resources=[f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{ssm_secret_prefix}/*"],
            )
        )
        news_lambda.add_to_role_policy(
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

        if is_prod:
            for lang, schedules in _LANG_SCHEDULE.items():
                chat_ids = chats.get(lang, [])
                if not chat_ids:
                    continue
                for hour_utc, minute_utc in schedules:
                    slot = f"{hour_utc:02d}{minute_utc:02d}"
                    rule = events.Rule(
                        self,
                        f"{CONSTRUCT_PREFIX}NewsRule{lang.upper()}{slot}",
                        rule_name=f"{RESOURCE_PREFIX}-news-{lang}-{slot}-{env_name}",
                        description=f"Trigger news lambda at {hour_utc:02d}:{minute_utc:02d} UTC for {lang} chats",
                        schedule=events.Schedule.cron(
                            minute=str(minute_utc),
                            hour=str(hour_utc),
                            day="*",
                            month="*",
                            year="*",
                        ),
                    )
                    rule.add_target(
                        events_targets.LambdaFunction(
                            news_lambda,
                            event=events.RuleTargetInput.from_object(
                                {
                                    "chat_ids": chat_ids,
                                    "lang": lang,
                                }
                            ),
                        )
                    )
