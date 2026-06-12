from __future__ import annotations

import json

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigwv2
from aws_cdk import aws_apigatewayv2_integrations as apigwv2_integrations
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class BotConstruct(Construct):
    """One bot Lambda: API Gateway webhook and SQS consumer.

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
        vector_queue: sqs.Queue,
        admin_user_id: str,
        gemini_api_base: str,
        gemini_model: str,
        gemini_rpd_limit: int,
        gemini_embedding_rpd_limit: str,
        groq_api_base: str,
        groq_model: str,
        spam_rule_enforce_threshold: str,
        spam_rule_ai_threshold: str,
        spam_ai_confidence_threshold: str,
        chat_lang_map: dict[str, str],
        captcha_timeout_seconds: int,
        captcha_max_attempts: int,
        kick_ban_duration_seconds: int,
        voteban_threshold: int,
        voteban_forgive_threshold: int,
        group_memory_enabled: str,
        group_memory_recent_limit: str,
        group_memory_retention_days: str,
        group_memory_extractor_provider: str,
        group_memory_extractor_mode: str,
        group_memory_extractor_min_confidence: str,
        group_memory_extractor_daily_llm_limit: str,
        group_memory_extractor_per_chat_daily_limit: str,
        group_memory_daily_summary_days: str,
        group_memory_daily_summary_message_limit: str,
        agent_enabled: str,
        agent_bot_username: str,
        agent_recent_context_limit: str,
        agent_daily_proactive_limit: str,
        agent_proactive_score_threshold: str,
        agent_proactive_final_threshold: str,
        vector_memory_enabled: str,
        vector_memory_provider: str,
        vector_memory_dimensions: str,
        vector_memory_embedding_model: str,
        vector_memory_index_throttle_seconds: str,
        vector_memory_backfill_batch_size: str,
        vector_memory_max_distance: str,
        vector_memory_vector_bucket_name: str | None = None,
        vector_memory_index_name: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        vector_memory_create_resources = (
            vector_memory_enabled.strip().lower() in {"1", "true", "yes", "on"}
            and vector_memory_provider.strip().lower() == "s3_vectors"
        )
        vector_bucket_name = vector_memory_vector_bucket_name or f"{RESOURCE_PREFIX}-memory-vectors-{env_name}"
        vector_index_name = vector_memory_index_name or f"{RESOURCE_PREFIX}-group-memory-{env_name}"

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

        memory_table = dynamodb.Table(
            self,
            f"{CONSTRUCT_PREFIX}MemoryTable",
            table_name=f"{RESOURCE_PREFIX}-bot-memory-{env_name}",
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
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

        vector_bucket: s3vectors.CfnVectorBucket | None = None
        vector_index: s3vectors.CfnIndex | None = None
        if vector_memory_create_resources:
            vector_bucket = s3vectors.CfnVectorBucket(
                self,
                f"{CONSTRUCT_PREFIX}MemoryVectorBucket",
                vector_bucket_name=vector_bucket_name,
            )
            vector_bucket.apply_removal_policy(removal_policy)
            vector_index = s3vectors.CfnIndex(
                self,
                f"{CONSTRUCT_PREFIX}MemoryVectorIndex",
                vector_bucket_name=vector_bucket.vector_bucket_name,
                index_name=vector_index_name,
                data_type="float32",
                dimension=int(vector_memory_dimensions),
                distance_metric="cosine",
                metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                    non_filterable_metadata_keys=["text"],
                ),
            )
            vector_index.add_dependency(vector_bucket)
            vector_index.apply_removal_policy(removal_policy)

        bot_environment = {
            "LOG_LEVEL": log_level,
            "TELEGRAM_API_BASE": telegram_api_base,
            "DEFAULT_LANG": default_lang,
            # -- SSM secret prefix (secrets fetched at runtime, not baked in) ──
            "SSM_SECRET_PREFIX": ssm_secret_prefix,
            # -- Non-secret bot parameters ─────────────────────────────────────
            "STATS_TABLE_NAME": stats_table.table_name,
            "MEMORY_TABLE_NAME": memory_table.table_name,
            "QUEUE_URL": queue.queue_url,
            "VECTOR_MEMORY_QUEUE_URL": vector_queue.queue_url,
            "ADMIN_USER_ID": admin_user_id,
            # -- Group memory / agent MVP ─────────────────────────────────────
            "GROUP_MEMORY_ENABLED": group_memory_enabled,
            "GROUP_MEMORY_RECENT_LIMIT": group_memory_recent_limit,
            "GROUP_MEMORY_RETENTION_DAYS": group_memory_retention_days,
            "GROUP_MEMORY_EXTRACTOR_PROVIDER": group_memory_extractor_provider,
            "GROUP_MEMORY_EXTRACTOR_MODE": group_memory_extractor_mode,
            "GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE": group_memory_extractor_min_confidence,
            "GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT": group_memory_extractor_daily_llm_limit,
            "GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT": group_memory_extractor_per_chat_daily_limit,
            "GROUP_MEMORY_DAILY_SUMMARY_DAYS": group_memory_daily_summary_days,
            "GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT": group_memory_daily_summary_message_limit,
            "VECTOR_MEMORY_ENABLED": vector_memory_enabled,
            "VECTOR_MEMORY_PROVIDER": vector_memory_provider if vector_memory_create_resources else "",
            "VECTOR_MEMORY_VECTOR_BUCKET_NAME": vector_bucket_name if vector_memory_create_resources else "",
            "VECTOR_MEMORY_INDEX_NAME": vector_index_name if vector_memory_create_resources else "",
            "VECTOR_MEMORY_DIMENSIONS": vector_memory_dimensions,
            "VECTOR_MEMORY_EMBEDDING_MODEL": vector_memory_embedding_model,
            "VECTOR_MEMORY_INDEX_THROTTLE_SECONDS": vector_memory_index_throttle_seconds,
            "VECTOR_MEMORY_BACKFILL_BATCH_SIZE": vector_memory_backfill_batch_size,
            "VECTOR_MEMORY_MAX_DISTANCE": vector_memory_max_distance,
            "AGENT_ENABLED": agent_enabled,
            "AGENT_BOT_USERNAME": agent_bot_username,
            "AGENT_RECENT_CONTEXT_LIMIT": agent_recent_context_limit,
            "AGENT_DAILY_PROACTIVE_LIMIT": agent_daily_proactive_limit,
            "AGENT_PROACTIVE_SCORE_THRESHOLD": agent_proactive_score_threshold,
            "AGENT_PROACTIVE_FINAL_THRESHOLD": agent_proactive_final_threshold,
            # -- Groq parameters (non-secret) ──────────────────────────────────
            "GROQ_API_BASE": groq_api_base,
            "GROQ_MODEL": groq_model,
            "SPAM_RULE_ENFORCE_THRESHOLD": spam_rule_enforce_threshold,
            "SPAM_RULE_AI_THRESHOLD": spam_rule_ai_threshold,
            "SPAM_AI_CONFIDENCE_THRESHOLD": spam_ai_confidence_threshold,
            # -- Gemini parameters (non-secret) ────────────────────────────────
            "GEMINI_API_BASE": gemini_api_base,
            "GEMINI_MODEL": gemini_model,
            "GEMINI_RPD_LIMIT": gemini_rpd_limit,
            "GEMINI_EMBEDDING_RPD_LIMIT": gemini_embedding_rpd_limit,
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
            timeout=Duration.seconds(300),
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

        self.handler_lambda = webhook_lambda
        self.stats_table = stats_table
        self.memory_table = memory_table
        self.vector_bucket = vector_bucket
        self.vector_index = vector_index
        self.bot_environment = bot_environment

        # Grant least-privilege SSM read access for secrets under the env prefix.
        stack = Stack.of(self)

        # Handlers (webhook and SQS path) use the same SSM parameters.
        bot_ssm_secret_names = [
            "bot-token",
            "webhook-secret-token",
            "groq-api-key",
            "gemini-api-key",
            "gemini-embedding-api-key",
            "deepseek-api-key",
        ]

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

        grant_secret_access(webhook_lambda, bot_ssm_secret_names)

        queue.grant_send_messages(webhook_lambda)
        queue.grant_consume_messages(webhook_lambda)
        vector_queue.grant_send_messages(webhook_lambda)
        stats_table.grant_read_write_data(webhook_lambda)
        memory_table.grant_read_write_data(webhook_lambda)
        if vector_bucket is not None and vector_index is not None:
            webhook_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    sid="UseZerdeMemoryVectors",
                    actions=[
                        "s3vectors:QueryVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:DeleteVectors",
                        "s3vectors:GetIndex",
                    ],
                    resources=[
                        vector_bucket.attr_vector_bucket_arn,
                        vector_index.attr_index_arn,
                    ],
                )
            )

        webhook_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue,
                batch_size=1,
                max_batching_window=Duration.seconds(0),
                max_concurrency=10,
            )
        )

        if is_prod and chat_lang_map:
            summary_rule = events.Rule(
                self,
                f"{CONSTRUCT_PREFIX}DailyGroupSummaryRule",
                rule_name=f"{RESOURCE_PREFIX}-group-memory-daily-summary-{env_name}",
                description="Queue daily group memory summaries for configured chats",
                schedule=events.Schedule.cron(minute="55", hour="20", day="*", month="*", year="*"),
            )
            summary_rule.add_target(
                events_targets.SqsQueue(
                    queue,
                    message=events.RuleTargetInput.from_object(
                        {
                            "task_type": "PROCESS_DAILY_GROUP_SUMMARIES",
                            "chat_ids": sorted(chat_lang_map.keys()),
                        }
                    ),
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
