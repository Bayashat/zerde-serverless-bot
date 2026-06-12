from __future__ import annotations

from typing import Any

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_sqs as sqs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from components.constants import CONSTRUCT_PREFIX, LAMBDA_RUNTIME, PROJECT_ROOT, RESOURCE_PREFIX
from constructs import Construct


class VectorIndexerConstruct(Construct):
    """Dedicated Lambda for vector memory indexing and backfill SQS tasks."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        shared_layer: _lambda.ILayer,
        env_name: str,
        is_prod: bool,
        ssm_secret_prefix: str,
        vector_queue: sqs.Queue,
        memory_table: dynamodb.Table,
        stats_table: dynamodb.Table,
        vector_bucket: s3vectors.CfnVectorBucket | None,
        vector_index: s3vectors.CfnIndex | None,
        environment: dict[str, Any],
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY
        vector_indexer_lambda = PythonFunction(
            self,
            f"{CONSTRUCT_PREFIX}VectorIndexerLambda",
            function_name=f"{RESOURCE_PREFIX}-vector-indexer-{env_name}",
            entry=str(PROJECT_ROOT / "src" / "bot"),
            index="vector_indexer_main.py",
            handler="lambda_handler",
            runtime=LAMBDA_RUNTIME,
            architecture=_lambda.Architecture.ARM_64,
            layers=[shared_layer],
            timeout=Duration.seconds(300),
            memory_size=1024,
            log_group=logs.LogGroup(
                self,
                f"{CONSTRUCT_PREFIX}VectorIndexerLogGroup",
                log_group_name=f"/aws/lambda/{RESOURCE_PREFIX}-vector-indexer-{env_name}",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=removal_policy,
            ),
            environment=environment,
        )

        self.handler_lambda = vector_indexer_lambda

        stack = Stack.of(self)
        vector_indexer_ssm_secret_names = [
            "gemini-api-key",
            "gemini-embedding-api-key",
        ]
        vector_indexer_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="ReadZerdeVectorIndexerSSMSecrets",
                actions=["ssm:GetParameters"],
                resources=[
                    f"arn:aws:ssm:{stack.region}:{stack.account}:parameter{ssm_secret_prefix}/{name}"
                    for name in vector_indexer_ssm_secret_names
                ],
            )
        )
        vector_indexer_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="DecryptZerdeVectorIndexerSSMSecrets",
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

        vector_queue.grant_consume_messages(vector_indexer_lambda)
        vector_queue.grant_send_messages(vector_indexer_lambda)
        memory_table.grant_read_write_data(vector_indexer_lambda)
        # Embedding quota counters live in the stats table; keep this narrower than bot access.
        stats_table.grant(vector_indexer_lambda, "dynamodb:GetItem", "dynamodb:UpdateItem")
        if vector_bucket is not None and vector_index is not None:
            vector_indexer_lambda.add_to_role_policy(
                iam.PolicyStatement(
                    sid="UseZerdeMemoryVectors",
                    actions=[
                        "s3vectors:PutVectors",
                        "s3vectors:QueryVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:DeleteVectors",
                        "s3vectors:ListVectors",
                        "s3vectors:GetIndex",
                    ],
                    resources=[
                        vector_bucket.attr_vector_bucket_arn,
                        vector_index.attr_index_arn,
                    ],
                )
            )

        vector_indexer_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                vector_queue,
                batch_size=1,
                max_batching_window=Duration.seconds(0),
                max_concurrency=3,
            )
        )
