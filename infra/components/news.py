from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct

# Language → list of (hour_utc, minute_utc) trigger times
_LANG_SCHEDULE: dict[str, list[tuple[int, int]]] = {
    "kk": [(4, 0), (14, 0)],  # 04:00 and 14:00 UTC
    "zh": [(4, 2), (14, 2)],  # 04:02 and 14:02 UTC
    "ru": [(4, 4)],  # 04:04 UTC only
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
        bot_token: str,
        gemini_api_key: str,
        news_chats: dict[str, list[str]],
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
                "LOG_LEVEL": log_level,
                "BOT_TOKEN": bot_token,
                "GEMINI_API_KEY": gemini_api_key,
                "AI_PROVIDER": ai_provider,
                "LLM_MODEL": llm_model,
            },
        )

        if is_prod:
            for lang, schedules in _LANG_SCHEDULE.items():
                chat_ids = news_chats.get(lang, [])
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
