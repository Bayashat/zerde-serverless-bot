from __future__ import annotations

import json

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class BotConstruct(Construct):
    """Bot Lambda: API Gateway webhook + SQS timeout tasks.

    Exposes:
        api (apigwv2.HttpApi): HTTP API used by stack for CfnOutput.
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
        default_lang: str,
        bot_token: str,
        webhook_secret_token: str,
        queue: sqs.Queue,
        admin_user_id: str,
        gemini_api_base: str,
        gemini_api_key: str,
        wtf_gemini_model: str,
        gemini_rpd_limit: int,
        groq_api_base: str,
        groq_api_key: str,
        groq_model: str,
        llama_api_base: str,
        llama_api_key: str,
        llama_model: str,
        deepseek_api_base: str,
        deepseek_api_key: str,
        deepseek_model: str,
        wtf_fallback_provider: str,
        chat_lang_map: dict[str, str],
        captcha_timeout_seconds: int,
        kick_ban_duration_seconds: int,
        voteban_threshold: int,
        voteban_forgive_threshold: int,
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        stats_table = dynamodb.Table(
            self,
            f"{CONSTRUCT_PREFIX}StatsTable",
            table_name=f"{RESOURCE_PREFIX}-bot-stats-{env_name}",
            partition_key=dynamodb.Attribute(
                name="stat_key",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
            deletion_protection=is_prod,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=is_prod
            ),
            time_to_live_attribute="ttl",
        )

        handler_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}BotLambda",
            function_name=f"{RESOURCE_PREFIX}-bot-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.seconds(90),
            memory_size=1024,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}BotLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-bot-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment={
                "LOG_LEVEL": log_level,
                "TELEGRAM_API_BASE": telegram_api_base,
                "DEFAULT_LANG": default_lang,
                # -- Bot parameters ────────────────────────────────────────────────
                "BOT_TOKEN": bot_token,
                "WEBHOOK_SECRET_TOKEN": webhook_secret_token,
                "STATS_TABLE_NAME": stats_table.table_name,
                "QUEUE_URL": queue.queue_url,
                "ADMIN_USER_ID": admin_user_id,
                # -- Groq parameters ────────────────────────────────────────────────
                "GROQ_API_BASE": groq_api_base,
                "GROQ_API_KEY": groq_api_key,
                "GROQ_MODEL": groq_model,
                # -- Llama parameters ──────────────────────────────────────────────
                "LLAMA_API_BASE": llama_api_base,
                "LLAMA_API_KEY": llama_api_key,
                "LLAMA_MODEL": llama_model,
                # -- DeepSeek parameters ────────────────────────────────────────────
                "DEEPSEEK_API_BASE": deepseek_api_base,
                "DEEPSEEK_API_KEY": deepseek_api_key,
                "DEEPSEEK_MODEL": deepseek_model,
                # -- WTF fallback provider ──────────────────────────────────────────
                "WTF_FALLBACK_PROVIDER": wtf_fallback_provider,
                # -- Gemini parameters ───────────────────────────────────────────────
                "GEMINI_API_BASE": gemini_api_base,
                "GEMINI_API_KEY": gemini_api_key,
                "WTF_GEMINI_MODEL": wtf_gemini_model,
                "GEMINI_RPD_LIMIT": gemini_rpd_limit,
                # -- Chat → language mapping (JSON string for Lambda env) ─────────────
                "CHAT_LANG_MAP": json.dumps(chat_lang_map),
                # -- Timing parameters ────────────────────────────────────────────────
                "CAPTCHA_TIMEOUT_SECONDS": captcha_timeout_seconds,
                "KICK_BAN_DURATION_SECONDS": kick_ban_duration_seconds,
                # -- Vote-to-ban thresholds ──────────────────────────────────────────
                "VOTEBAN_THRESHOLD": voteban_threshold,
                "VOTEBAN_FORGIVE_THRESHOLD": voteban_forgive_threshold,
            },
        )

        self.handler_lambda = handler_lambda

        queue.grant_consume_messages(handler_lambda)
        queue.grant_send_messages(handler_lambda)
        stats_table.grant_read_write_data(handler_lambda)

        handler_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue,
                batch_size=1,
                max_batching_window=Duration.seconds(0),
                max_concurrency=10,
            )
        )

        self.api = apigwv2.HttpApi(
            self,
            f"{CONSTRUCT_PREFIX}HttpApi",
            api_name=f"{RESOURCE_PREFIX}-webhook-api-{env_name}",
        )

        self.api.add_routes(
            path="/webhook",
            methods=[apigwv2.HttpMethod.POST],
            integration=apigwv2_integrations.HttpLambdaIntegration(
                f"{CONSTRUCT_PREFIX}WebhookIntegration",
                handler=handler_lambda,
            ),
        )
