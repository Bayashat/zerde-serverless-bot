from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aws_cdk import BundlingOptions, CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sqs as sqs
from constructs import Construct
from dotenv import load_dotenv


class TelegramBotStack(Stack):
    """CDK stack defining the Telegram bot serverless architecture."""

    def __init__(self, scope: Construct, construct_id: str, env_name: str = "dev", **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Environment configuration
        is_prod = env_name == "prod"

        # Get project root directory (parent of infrastructure/)
        project_root = Path(__file__).parent.parent

        # Load environment variables from .env file
        load_dotenv(dotenv_path=project_root / ".env")

        # Telegram Bot Token and Webhook Secret Token
        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        telegram_webhook_secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET_TOKEN")

        if not telegram_bot_token or not telegram_webhook_secret_token:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET_TOKEN must be set")

        project_name_prefix = f"Zerde{env_name.capitalize()}"
        stack_name_prefix = f"zerde-{env_name}"

        exclude_files = [".venv", ".venv/**", "__pycache__", "__pycache__/**", ".pyc", ".DS_Store", ".git", "tests"]

        # ============================================================================
        # Common Environment Variables
        # ============================================================================
        # Log level: INFO for prod, DEBUG for dev
        log_level = "INFO" if is_prod else "DEBUG"

        self.common_env_vars = {
            "POWERTOOLS_LOG_LEVEL": log_level,
            "ENV_NAME": env_name,
        }

        # ============================================================================
        # DynamoDB Tables
        # ============================================================================

        # DynamoDB configuration based on environment
        if is_prod:
            removal_policy = RemovalPolicy.RETAIN
            deletion_protection = True
            pitr_enabled = True
        else:
            # Development: DESTROY policy, no PITR
            removal_policy = RemovalPolicy.DESTROY
            deletion_protection = False
            pitr_enabled = False

        # Bot Statistics Table
        bot_stats_table_kwargs = {
            "id": f"{project_name_prefix}BotStatsTable",
            "table_name": f"{stack_name_prefix}-bot-stats",
            "partition_key": dynamodb.Attribute(
                name="stat_key",
                type=dynamodb.AttributeType.STRING,
            ),
            "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
            "removal_policy": removal_policy,
            "deletion_protection": deletion_protection,
        }
        if is_prod:
            bot_stats_table_kwargs["point_in_time_recovery_specification"] = dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=pitr_enabled
            )

        self.bot_stats_table = dynamodb.Table(self, **bot_stats_table_kwargs)

        # ============================================================================
        # SQS Queues
        # ============================================================================

        # Removal policy: RETAIN for prod, DESTROY for dev
        queue_removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        # SQS dead-letter queue
        self.dlq = sqs.Queue(
            self,
            f"{project_name_prefix}UpdatesDlq",
            queue_name=f"{stack_name_prefix}-updates-dlq",
            retention_period=Duration.days(7),
            removal_policy=queue_removal_policy,
        )

        # Main updates Queue
        self.updates_queue = sqs.Queue(
            self,
            f"{project_name_prefix}UpdatesQueue",
            queue_name=f"{stack_name_prefix}-updates-queue",
            retention_period=Duration.hours(1),
            visibility_timeout=Duration.seconds(90),
            receive_message_wait_time=Duration.seconds(20),
            removal_policy=queue_removal_policy,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=self.dlq,
            ),
        )
        # ============================================================================
        # Lambda Functions
        # ============================================================================

        # Common Lambda configuration
        lambda_runtime = _lambda.Runtime.PYTHON_3_13

        # Receiver Lambda - HTTP API entrypoint from Telegram webhook
        self.receiver_lambda = _lambda.Function(
            self,
            f"{project_name_prefix}ReceiverLambda",
            function_name=f"{stack_name_prefix}-receiver",
            runtime=lambda_runtime,
            handler="main.lambda_handler",
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            code=_lambda.Code.from_asset(
                str(project_root / "src" / "receiver"),
                exclude=exclude_files,
                bundling=BundlingOptions(
                    image=lambda_runtime.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            environment={
                **self.common_env_vars,
                "QUEUE_URL": self.updates_queue.queue_url,
                "WEBHOOK_SECRET_TOKEN": telegram_webhook_secret_token,
            },
        )

        # Least-privilege grants
        self.updates_queue.grant_send_messages(self.receiver_lambda)

        # Worker Lambda - processes queue messages and talks to DynamoDB / Telegram API
        self.worker_lambda = _lambda.Function(
            self,
            f"{project_name_prefix}WorkerLambda",
            function_name=f"{stack_name_prefix}-worker",
            runtime=lambda_runtime,
            architecture=_lambda.Architecture.ARM_64,
            handler="main.lambda_handler",
            timeout=Duration.seconds(60),
            log_retention=logs.RetentionDays.ONE_WEEK,
            code=_lambda.Code.from_asset(
                str(project_root / "src" / "worker"),
                exclude=exclude_files,
                bundling=BundlingOptions(
                    image=lambda_runtime.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        (
                            "pip install --no-cache-dir "
                            "--platform manylinux2014_aarch64 "
                            "--implementation cp "
                            "--python-version 3.13 "
                            "--only-binary=:all: "
                            "--upgrade "
                            "-r requirements.txt "
                            "-t /asset-output "
                            "&& cp -au . /asset-output"
                        ),
                    ],
                ),
            ),
            environment={
                **self.common_env_vars,
                "QUEUE_URL": self.updates_queue.queue_url,
                "DEFAULT_LANG": "en",
                "TELEGRAM_API_BASE": "https://api.telegram.org/bot",
                "BOT_TOKEN": telegram_bot_token,
                "WEBHOOK_SECRET_TOKEN": telegram_webhook_secret_token,
                "STATS_TABLE_NAME": self.bot_stats_table.table_name,
                "BOT_NAME": "Zerde Bot",
                "BOT_DESCRIPTION": "Zerde Bot Description",
                "BOT_INSTRUCTIONS": "Zerde Bot Instructions",
            },
        )

        # Grant least-privilege access to the worker lambda
        self.updates_queue.grant_consume_messages(self.worker_lambda)
        self.updates_queue.grant_send_messages(self.worker_lambda)  # For CHECK_TIMEOUT events
        self.bot_stats_table.grant_read_write_data(self.worker_lambda)

        # Add SQS event source with max concurrency of 2
        self.worker_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                self.updates_queue,
                batch_size=1,  # Process one message at a time
                max_batching_window=Duration.seconds(0),
                max_concurrency=10,  # Maximum concurrent invocations from SQS
            ),
        )

        # ============================================================================
        # API Gateway (HTTP API)
        # ============================================================================

        # API Gateway integrating with the receiver lambda
        self.webhook_api = apigwv2.HttpApi(
            self,
            f"{project_name_prefix}WebhookApi",
            api_name=f"{stack_name_prefix}-webhook-api",
        )

        webhook_integration = apigwv2_integrations.HttpLambdaIntegration(
            f"{project_name_prefix}WebhookIntegration",
            handler=self.receiver_lambda,
        )

        # Add POST /webhook route
        self.webhook_api.add_routes(
            path="/webhook",
            methods=[apigwv2.HttpMethod.POST],
            integration=webhook_integration,
        )

        # ============================================================================
        # Outputs
        # ============================================================================

        # Export the API endpoint so it can be used for Telegram webhook configuration
        CfnOutput(
            self,
            f"{project_name_prefix}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{stack_name_prefix}-webhook-api-url",
            value=self.webhook_api.url,
        )
