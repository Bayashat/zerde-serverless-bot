"""Lazy, namespace-qualified Memory V2 composition shared by bot and worker."""

import os

from core.config import MEMORY_V2_TABLE_NAME

_repo = None
_ingestion = None
_budget = None


def get_memory_v2_repo():
    global _repo
    if not MEMORY_V2_TABLE_NAME:
        return None
    if _repo is None:
        from .repository import MemoryRepository

        _repo = MemoryRepository(MEMORY_V2_TABLE_NAME)
    return _repo


def get_memory_ingestion():
    global _ingestion
    queue_url = os.environ.get("MEMORY_V2_QUEUE_URL")
    if not MEMORY_V2_TABLE_NAME or not queue_url:
        return None
    if _ingestion is None:
        from services.repositories.spam import SpamRepository

        from .ingestion import MemoryIngestion, MemoryQueue

        _ingestion = MemoryIngestion(get_memory_v2_repo(), SpamRepository(), MemoryQueue(queue_url))
    return _ingestion


def get_memory_budget():
    global _budget
    if _budget is None:
        from services.memory_budget import MemoryBudgetRepository

        _budget = MemoryBudgetRepository(os.environ.get("MEMORY_BUDGET_TABLE_NAME", ""))
    return _budget
