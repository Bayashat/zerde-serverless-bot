"""Dedicated reference-only Memory V2 worker and bounded recovery entrypoint."""

import asyncio

from botocore.exceptions import ClientError
from core.config import CHAT_LANG_MAP, get_gemini_api_key
from core.logger import LoggerAdapter, get_logger
from services.memory_v2.cost_runtime import metered
from services.memory_v2.extraction_prompt import input_upper_bytes
from services.memory_v2.extractor import MemoryExtractor
from services.memory_v2.gemini_extraction import GeminiExtractionProvider
from services.memory_v2.recovery import MemoryRecovery
from services.memory_v2.runtime import get_memory_budget, get_memory_ingestion, get_memory_v2_repo
from services.memory_v2.trend_runtime import maintain as maintain_trends
from services.memory_v2.worker import MemoryWorker

logger = LoggerAdapter(get_logger(__name__), {})
_RECOVERY_ERROR_TYPES = frozenset(
    {
        "MemoryPurgeRecoveryError",
        "MemoryRecoveryError",
        "MemoryConflict",
        "MemorySourceConflict",
        "MemoryUnavailable",
        "MemoryLearningPaused",
        "MemoryInputError",
        "TimeoutError",
        "ConnectionError",
        "ValueError",
        "TypeError",
        "KeyError",
        "RuntimeError",
        "BotoCoreError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "EndpointConnectionError",
        "ConnectionClosedError",
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
    }
)
_RECOVERY_AWS_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "ConditionalCheckFailedException",
        "TransactionCanceledException",
        "TransactionConflictException",
        "ProvisionedThroughputExceededException",
        "RequestLimitExceeded",
        "Throttling",
        "ThrottlingException",
        "ResourceNotFoundException",
        "ValidationException",
        "InternalServerError",
        "ServiceUnavailable",
        "QueueDoesNotExist",
        "AWS.SimpleQueueService.NonExistentQueue",
    }
)


def _recovery_error_fields(exc):
    # Even an exception class/code can be dynamically constructed from input.
    # Only fixed labels leave this boundary; never format the exception itself.
    name = type(exc).__name__
    fields = {"error_type": name if name in _RECOVERY_ERROR_TYPES else "UnexpectedError"}
    if isinstance(exc, ClientError):
        fields["error_type"] = "ClientError"
        response = exc.response
        error = response.get("Error") if isinstance(response, dict) else None
        code = error.get("Code") if isinstance(error, dict) else None
        fields["aws_error_code"] = code if isinstance(code, str) and code in _RECOVERY_AWS_CODES else "OtherAwsError"
    return fields


@metered(touch_first=True)
def lambda_handler(event, context):
    if event == {"schema": 2, "task_type": "RECOVER_MEMORY_V2"}:
        ingestion = get_memory_ingestion()
        if ingestion is None:
            raise RuntimeError("Memory V2 recovery is not configured")
        from services.memory_v2.lifecycle import MemoryLifecycle

        results, failures = {}, []
        for name, operation in (
            ("purges", lambda: MemoryLifecycle(ingestion.repo).recover(max_pages=2, runtime_seconds=20)),
            ("ingestion", lambda: MemoryRecovery(ingestion, runtime_seconds=60).run(max_pages=4)),
            ("trends", lambda: maintain_trends(ingestion.repo, chat_ids=CHAT_LANG_MAP, runtime_seconds=15)),
        ):
            try:
                results[name] = operation()
            except Exception as exc:
                logger.warning(
                    "Memory recovery stage remains pending", extra={"stage": name, **_recovery_error_fields(exc)}
                )
                failures.append(name)
        if failures:
            raise RuntimeError("Durable memory recovery remains pending")
        return results
    records = event.get("Records")
    if not isinstance(records, list) or not records or any(row.get("eventSource") != "aws:sqs" for row in records):
        raise ValueError("Unsupported Memory V2 event")
    repo = get_memory_v2_repo()
    if repo is None:
        raise RuntimeError("Memory V2 storage is not configured")

    def extractor_factory(validate_sources):
        return MemoryExtractor(
            provider=GeminiExtractionProvider(get_gemini_api_key()),
            budget=get_memory_budget(),
            validate_sources=validate_sources,
        )

    # Contributions do not wait for model extraction; periodic source traversal
    # recovers missed work. Unexpected storage errors retry this reference batch.
    maintain_trends(repo, records=records, runtime_seconds=10)
    worker = MemoryWorker(repo, extractor_factory, sizing_fn=input_upper_bytes, runtime_seconds=90)
    return asyncio.run(worker.handle_records(records))
