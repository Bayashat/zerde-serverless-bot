"""Helpers to keep LLM output compatible with Telegram HTML parse mode."""

from __future__ import annotations

import html
import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`]+)`")
_BULLET_RE = re.compile(r"^\s*[-*]\s+")
_CODE_PLACEHOLDER = "\u0000CODE{}END\u0000"


def fit_llm_output(text: str, *, max_chars: int) -> str:
    """Trim model text before Telegram HTML normalization."""
    cleaned = (text or "").strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned

    suffix = "..."
    cut_limit = max(1, max_chars - len(suffix))
    boundary = max(
        cleaned.rfind("\n\n", 0, cut_limit),
        cleaned.rfind(". ", 0, cut_limit),
        cleaned.rfind("! ", 0, cut_limit),
        cleaned.rfind("? ", 0, cut_limit),
    )
    if boundary < cut_limit * 0.55:
        boundary = cleaned.rfind(" ", 0, cut_limit)
    if boundary < cut_limit * 0.55:
        boundary = cut_limit
    return cleaned[:boundary].rstrip() + suffix


def normalize_llm_output_for_telegram_html(text: str) -> str:
    """Convert common markdown-like fragments into Telegram-safe HTML subset."""
    lines = text.splitlines()
    normalized_lines: list[str] = []
    for line in lines:
        normalized_lines.append(_BULLET_RE.sub("• ", line))

    normalized = html.escape("\n".join(normalized_lines), quote=False)
    code_fragments: list[str] = []

    def _stash_code(match: re.Match[str]) -> str:
        code_fragments.append(f"<code>{match.group(1)}</code>")
        return _CODE_PLACEHOLDER.format(len(code_fragments) - 1)

    normalized = _CODE_RE.sub(_stash_code, normalized)
    normalized = _BOLD_RE.sub(r"<b>\1</b>", normalized)
    normalized = _ITALIC_RE.sub(r"<i>\1</i>", normalized)
    for index, fragment in enumerate(code_fragments):
        normalized = normalized.replace(_CODE_PLACEHOLDER.format(index), fragment)
    return normalized
