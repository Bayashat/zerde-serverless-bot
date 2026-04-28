"""Helpers to keep LLM output compatible with Telegram HTML parse mode."""

from __future__ import annotations

import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BULLET_RE = re.compile(r"^\s*[-*]\s+")


def normalize_llm_output_for_telegram_html(text: str) -> str:
    """Convert common markdown-like fragments into Telegram-safe HTML subset."""
    lines = text.splitlines()
    normalized_lines: list[str] = []
    for line in lines:
        normalized_lines.append(_BULLET_RE.sub("• ", line))

    normalized = "\n".join(normalized_lines)
    normalized = _BOLD_RE.sub(r"<b>\1</b>", normalized)
    normalized = _CODE_RE.sub(r"<code>\1</code>", normalized)
    normalized = _ITALIC_RE.sub(r"<i>\1</i>", normalized)
    return normalized
