"""System prompts for /explain multimodal (voice, image, PDF) via Gemini."""

from __future__ import annotations

_LANG_NAMES = {"kk": "Kazakh", "ru": "Russian", "zh": "Simplified Chinese", "en": "English"}


def _output_language_clause(lang: str) -> str:
    name = _LANG_NAMES.get(lang, "the same language as the chat default")
    return (
        f"Write your entire answer in {name}. "
        "Output valid Telegram HTML only (<b>, <i>, <code>, <blockquote>). "
        "Do not use markdown syntax like **bold**, *italic*, or backticks."
    )


def transcribe_system_prompt(lang: str) -> str:
    """Transcribe speech; plain transcript only."""
    return (
        "You transcribe voice or audio messages. Output ONLY the spoken words as plain text. "
        "No preamble, no labels like 'Transcript:'. "
        "If unintelligible, say so in one short sentence. " + _output_language_clause(lang)
    )


def image_describe_system_prompt(lang: str) -> str:
    """Describe or answer about image content in a helpful neutral tone."""
    return (
        "You help users understand images: describe visible content, text in the image, UI, diagrams, "
        "or errors on screen. Be concise and accurate. No XML. "
        "If the user adds extra instructions in text, follow them. " + _output_language_clause(lang)
    )


def document_summary_system_prompt(lang: str) -> str:
    """Summarize PDF or plain-text documents."""
    return (
        "You summarize uploaded documents. Give: (1) a short overview, (2) 3-7 key points. "
        "Use either bullet lines with '•' or Telegram HTML list-like lines. No code fences unless essential. "
        "If the file is empty or unreadable, say so briefly. " + _output_language_clause(lang)
    )
