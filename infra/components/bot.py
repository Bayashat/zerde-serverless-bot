from __future__ import annotations

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
        queue: sqs.Queue,
        bot_token: str,
        webhook_secret_token: str,
        telegram_api_base: str,
        default_lang: str,
        log_level: str,
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
        )

        handler_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}BotLambda",
            function_name=f"{RESOURCE_PREFIX}-bot-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.X86_64,
            timeout=Duration.seconds(30),
            memory_size=256,
            snap_start=_lambda.SnapStartConf.ON_PUBLISHED_VERSIONS,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}BotLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-bot-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment={
                "POWERTOOLS_LOG_LEVEL": log_level,
                "ENV_NAME": env_name,
                "QUEUE_URL": queue.queue_url,
                "DEFAULT_LANG": default_lang,
                "BOT_TOKEN": bot_token,
                "WEBHOOK_SECRET_TOKEN": webhook_secret_token,
                "TELEGRAM_API_BASE": telegram_api_base,
                "STATS_TABLE_NAME": stats_table.table_name,
            },
        )

        queue.grant_consume_messages(handler_lambda)
        queue.grant_send_messages(handler_lambda)
        stats_table.grant_read_write_data(handler_lambda)

        # SnapStart requires invocation via a published version alias (not $LATEST).
        live_alias = _lambda.Alias(
            self,
            f"{CONSTRUCT_PREFIX}LiveAlias",
            alias_name="live",
            version=handler_lambda.current_version,
        )

        live_alias.add_event_source(
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
                handler=live_alias,
            ),
        )
