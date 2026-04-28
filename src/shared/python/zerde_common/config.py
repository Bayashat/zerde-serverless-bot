"""Typed environment variable helpers (shared across ZerdeBot Lambdas)."""

from __future__ import annotations

import json
import os
from typing import Any


def require(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"{key} must be set")
    return value


def require_int(key: str) -> int:
    """Return a required integer from the environment, with a clear error if missing or invalid."""
    raw = os.environ.get(key)
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        raise ValueError(f"{key} must be set to a non-empty integer")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a valid integer, got {raw!r}") from exc


def require_json(key: str) -> Any:
    """Return a required JSON value from the environment, with a clear error if missing or invalid."""
    raw = os.environ.get(key)
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        raise ValueError(f"{key} must be set to non-empty valid JSON")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{key} is not valid JSON: {exc}") from exc
