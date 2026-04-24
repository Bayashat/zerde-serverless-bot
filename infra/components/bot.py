from __future__ import annotations

import json

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class BotConstruct(Construct):
    """Bot webhook Lambda + single-purpose SQS task-worker Lambda.

    Exposes:
        api (apigwv2.HttpApi): HTTP API used by stack for CfnOutput.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        shared_layer: _lambda.ILayer,
        env_name: str,
        is_prod: bool,
        log_level: str,
        telegram_api_base: str,
        default_lang: str,
        ssm_secret_prefix: str,
        queue: sqs.Queue,
        admin_user_id: str,
        gemini_api_base: str,
        wtf_gemini_model: str,
        gemini_rpd_limit: int,
        groq_api_base: str,
        groq_model: str,
        deepseek_api_base: str,
        deepseek_model: str,
        chat_lang_map: dict[str, str],
        captcha_timeout_seconds: int,
        captcha_max_attempts: int,
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

        bot_environment = {
            "LOG_LEVEL": log_level,
            "TELEGRAM_API_BASE": telegram_api_base,
            "DEFAULT_LANG": default_lang,
            # -- SSM secret prefix (secrets fetched at runtime, not baked in) ──
            "SSM_SECRET_PREFIX": ssm_secret_prefix,
            # -- Non-secret bot parameters ─────────────────────────────────────
            "STATS_TABLE_NAME": stats_table.table_name,
            "QUEUE_URL": queue.queue_url,
            "ADMIN_USER_ID": admin_user_id,
            # -- Groq parameters (non-secret) ──────────────────────────────────
            "GROQ_API_BASE": groq_api_base,
            "GROQ_MODEL": groq_model,
            # -- DeepSeek parameters (non-secret) ──────────────────────────────
            "DEEPSEEK_API_BASE": deepseek_api_base,
            "DEEPSEEK_MODEL": deepseek_model,
            # -- Gemini parameters (non-secret) ────────────────────────────────
            "GEMINI_API_BASE": gemini_api_base,
            "WTF_GEMINI_MODEL": wtf_gemini_model,
            "GEMINI_RPD_LIMIT": gemini_rpd_limit,
            # -- Chat → language mapping ───────────────────────────────────────
            "CHAT_LANG_MAP": json.dumps(chat_lang_map),
            # -- Timing parameters ─────────────────────────────────────────────
            "CAPTCHA_TIMEOUT_SECONDS": captcha_timeout_seconds,
            "CAPTCHA_MAX_ATTEMPTS": captcha_max_attempts,
            "KICK_BAN_DURATION_SECONDS": kick_ban_duration_seconds,
            # -- Vote-to-ban thresholds ────────────────────────────────────────
            "VOTEBAN_THRESHOLD": voteban_threshold,
            "VOTEBAN_FORGIVE_THRESHOLD": voteban_forgive_threshold,
        }

        webhook_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}BotLambda",
            function_name=f"{RESOURCE_PREFIX}-bot-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            layers=[shared_layer],
            timeout=Duration.seconds(90),
            memory_size=1024,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}BotLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-bot-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment=bot_environment,
        )

        task_worker_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}BotTaskWorkerLambda",
            function_name=f"{RESOURCE_PREFIX}-bot-task-worker-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="task_worker.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            layers=[shared_layer],
            timeout=Duration.seconds(90),
            memory_size=1024,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}BotTaskWorkerLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-bot-task-worker-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment=bot_environment,
        )

        self.handler_lambda = webhook_lambda
        self.task_worker_lambda = task_worker_lambda

        # Grant least-privilege SSM read access for secrets under the env prefix.
        stack = Stack.of(self)

        def grant_secret_access(fn: _lambda.IFunction, secret_names: list[str]) -> None:
            fn.add_to_role_policy(
                iam.PolicyStatement(
                    sid="ReadZerdeSSMSecrets",
                    actions=["ssm:GetParameters"],
                    resources=[
                        f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{ssm_secret_prefix}/{name}"
                        for name in secret_names
                    ],
                )
            )
            fn.add_to_role_policy(
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

        grant_secret_access(webhook_lambda, ["bot-token", "webhook-secret-token"])
        grant_secret_access(task_worker_lambda, ["bot-token", "groq-api-key", "gemini-api-key", "deepseek-api-key"])

        queue.grant_send_messages(webhook_lambda)
        queue.grant_consume_messages(task_worker_lambda)
        stats_table.grant_read_write_data(webhook_lambda)
        stats_table.grant_read_write_data(task_worker_lambda)

        task_worker_lambda.add_event_source(
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
                handler=webhook_lambda,
            ),
        )
