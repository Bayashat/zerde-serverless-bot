"""Fail-closed boundary for the retired memory and automatic social features.

This is a code protocol, not a flag that old deployment settings can re-enable.
V2 will introduce its own versioned source-reference protocol and control owner.
"""

import time
from typing import Any

EXPLICIT_CONTEXT_VERSION = "explicit-only-2026-09"
RETIRED_TASK_TYPES = frozenset(
    {
        "PROCESS_PROACTIVE_CANDIDATE",
        "PROCESS_AMBIENT_REACTION",
        "PROCESS_GROUP_MEMORY",
        "PROCESS_DAILY_GROUP_SUMMARIES",
        "PROCESS_VECTOR_MEMORY",
        "PROCESS_VECTOR_MEMORY_BACKFILL",
    }
)


def is_current_explicit_task(body: dict[str, Any]) -> bool:
    return body.get("context_version") == EXPLICIT_CONTEXT_VERSION


def is_current_explicit_reply(item: dict[str, Any]) -> bool:
    """DynamoDB TTL is asynchronous; expired or legacy threads cannot be read."""
    try:
        return (
            item.get("context_version") == EXPLICIT_CONTEXT_VERSION
            and not item.get("retrieval_sources")
            and int(item.get("ttl", 0)) > int(time.time())
        )
    except (TypeError, ValueError):
        return False
