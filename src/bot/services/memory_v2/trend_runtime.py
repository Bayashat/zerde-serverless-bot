"""Budgeted, bounded maintenance of accepted-source topic contributions."""

import time

from services.memory_budget import MemoryBudgetPaused

from .models import MemoryInputError, MemoryUnavailable
from .runtime import get_memory_budget
from .trend_service import TrendService
from .worker import MemoryWorker


def maintain(repo, *, records=None, chat_ids=(), runtime_seconds=15):
    deadline = time.monotonic() + runtime_seconds
    counts = {"updated": 0, "obsolete": 0, "pending": 0, "paused": False}
    try:
        get_memory_budget().check_aws_available()
    except MemoryBudgetPaused:
        return {**counts, "paused": True}
    service = TrendService(repo)
    if records is not None:
        for record in records:
            if time.monotonic() >= deadline:
                counts["pending"] += 1
                continue
            try:
                chat, ref = MemoryWorker._parse(record)
                service.contribute(chat, ref)
            except (MemoryInputError, MemoryUnavailable, ValueError, KeyError, TypeError):
                counts["obsolete"] += 1
            else:
                counts["updated"] += 1
        return counts
    groups = sorted(set(str(chat) for chat in chat_ids))
    if groups:
        offset = (repo.now() // 300) % len(groups)
        groups = groups[offset:] + groups[:offset]
    for chat in groups:
        remaining = int(deadline - time.monotonic())
        if remaining < 1:
            counts["pending"] += 1
            continue
        try:
            result = service.refresh(chat, max_pages=1, page_size=10, runtime_seconds=min(15, remaining))
        except MemoryUnavailable:
            counts["obsolete"] += 1
        else:
            counts["updated"] += result["updated"]
            counts["pending"] += int(result["pending"])
    return counts
