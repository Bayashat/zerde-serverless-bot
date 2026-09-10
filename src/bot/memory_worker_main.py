"""Dedicated reference-only Memory V2 worker and bounded recovery entrypoint."""

import asyncio

from core.config import get_gemini_api_key
from services.memory_v2.extraction_prompt import input_upper_bytes
from services.memory_v2.extractor import MemoryExtractor
from services.memory_v2.gemini_extraction import GeminiExtractionProvider
from services.memory_v2.recovery import MemoryRecovery
from services.memory_v2.runtime import get_memory_budget, get_memory_ingestion, get_memory_v2_repo
from services.memory_v2.worker import MemoryWorker


def lambda_handler(event, context):
    if event == {"schema": 2, "task_type": "RECOVER_MEMORY_V2"}:
        ingestion = get_memory_ingestion()
        if ingestion is None:
            raise RuntimeError("Memory V2 recovery is not configured")
        return MemoryRecovery(ingestion).run(max_pages=4)
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

    worker = MemoryWorker(repo, extractor_factory, sizing_fn=input_upper_bytes)
    return asyncio.run(worker.handle_records(records))
