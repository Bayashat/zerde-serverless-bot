from __future__ import annotations

from aws_cdk import Duration, RemovalPolicy
from aws_cdk import aws_sqs as sqs
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
from constructs import Construct


class MessagingConstruct(Construct):
    """SQS dead-letter queue and timeout-tasks queue (CHECK_TIMEOUT tasks only)."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str,
        is_prod: bool,
    ) -> None:
        super().__init__(scope, construct_id)

        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        dlq = sqs.Queue(
            self,
            f"{CONSTRUCT_PREFIX}TimeoutTasksDlq",
            queue_name=f"{RESOURCE_PREFIX}-timeout-tasks-dlq-{env_name}",
            retention_period=Duration.hours(2),
            removal_policy=removal_policy,
        )

        self.queue = sqs.Queue(
            self,
            f"{CONSTRUCT_PREFIX}TimeoutTasksQueue",
            queue_name=f"{RESOURCE_PREFIX}-timeout-tasks-queue-{env_name}",
            retention_period=Duration.hours(1),
            visibility_timeout=Duration.seconds(60 * 3),
            receive_message_wait_time=Duration.seconds(20),
            removal_policy=removal_policy,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )
