"""Independent Memory V2 storage. Provisioning never enables learning."""

from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
from constructs import Construct


class MemoryV2Construct(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, env_name: str, is_prod: bool):
        super().__init__(scope, construct_id)
        self.table = dynamodb.Table(
            self,
            f"{CONSTRUCT_PREFIX}MemoryV2Table",
            table_name=f"{RESOURCE_PREFIX}-memory-v2-{env_name}",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY,
            deletion_protection=is_prod,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=is_prod,
                recovery_period_in_days=7 if is_prod else None,
            ),
        )
        # Sparse index: only pending or leased work has these attributes. Index
        # results are hints; the worker must strongly read authoritative rows.
        self.table.add_global_secondary_index(
            index_name="work-due",
            partition_key=dynamodb.Attribute(name="work_queue", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="due_at", type=dynamodb.AttributeType.NUMBER),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )
