from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class NewsConstruct(Construct):
    """Daily IT news digest: News Lambda + EventBridge schedules (prod-only).

    Exposes:
        function_name (str): used by stack for CfnOutput.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        is_prod: bool,
        bot_token: str,
        gemini_api_key: str,
        news_chat_ids: str,
        ai_provider: str,
        llm_model: str,
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
            architecture=_lambda.Architecture.X86_64,
            timeout=Duration.minutes(2),
            memory_size=256,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}NewsLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-news-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment={
                "POWERTOOLS_LOG_LEVEL": log_level,
                "ENV_NAME": env_name,
                "BOT_TOKEN": bot_token,
                "GEMINI_API_KEY": gemini_api_key,
                "NEWS_CHAT_IDS": news_chat_ids,
                "AI_PROVIDER": ai_provider,
                "LLM_MODEL": llm_model,
            },
        )

        if is_prod:
            for hour_utc, slot in [(4, "morning"), (14, "evening")]:
                rule = events.Rule(
                    self,
                    f"{CONSTRUCT_PREFIX}NewsRule{slot.capitalize()}",
                    rule_name=f"{RESOURCE_PREFIX}-news-{slot}-{env_name}",
                    description=f"Trigger news lambda at {hour_utc:02d}:00 UTC (daily digest {slot})",
                    schedule=events.Schedule.cron(
                        minute="0",
                        hour=str(hour_utc),
                        day="*",
                        month="*",
                        year="*",
                    ),
                )
                rule.add_target(events_targets.LambdaFunction(news_lambda))
