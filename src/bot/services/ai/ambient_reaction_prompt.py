"""Prompt construction for ambient emoji reaction classifiers."""

from __future__ import annotations


def build_ambient_reaction_prompts(
    *,
    current_message: str,
    previous_context: str = "",
    reply_context: str = "",
    allowed_emojis: tuple[str, ...] = ("🤣", "👍", "🤔", "❤️", "👀"),
    lang: str = "kk",
) -> tuple[str, str]:
    """Return system/user prompts shared by Gemini and OpenAI-compatible providers."""
    allowed = " ".join(allowed_emojis)
    system_prompt = (
        "You classify whether ZerdeBot should add one quiet emoji reaction to a Telegram group message. "
        "Most messages should receive no reaction. The correct default is should_react=false. "
        "React only when the signal is strong, natural, and safe in context. Do not be overly enthusiastic. "
        "Commands and sensitive, serious, hostile, sad, political, religious, ethnic conflict, medical, legal, "
        "or financial content are not automatic skips, but react only when the reaction would not trivialize, "
        "endorse, mock, or escalate the situation. "
        f"Use only these allowed emoji exactly: {allowed}. "
        "Emoji meanings: 🤣 humor/meme/joke; 👍 useful or high-quality technical/practical message; "
        "🤔 thoughtful technical question or complex reasoning; ❤️ warm, positive, thankful, or congratulatory; "
        "👀 interesting, surprising, worth noticing, but harmless. "
        "Return strict JSON only with keys: should_react (boolean), emoji (allowed emoji string or null), "
        "confidence (0..1), category (humor,useful,thoughtful,warm,interesting,none), reason (short string). "
        "If should_react=false, emoji must be null."
    )
    user_prompt = (
        f"Preferred language code: {lang}\n\n"
        "Allowed emojis:\n"
        f"{allowed}\n\n"
        "Decision rules:\n"
        "- Most messages get no reaction.\n"
        "- React only on a strong signal.\n"
        "- Commands may be considered; judge the command text and local conversation context.\n"
        "- Sensitive, serious, hostile, sad, crisis, political, religious, ethnic conflict, medical, legal, "
        "or financial content may be considered, but never react in a way that trivializes, mocks, endorses, "
        "or escalates harm.\n"
        "- Do not analyze media; this task receives text only.\n\n"
        "Previous local group context, oldest to newest:\n"
        f"{previous_context or '(no previous context)'}\n\n"
        "Reply context, immediate reply first when available:\n"
        f"{reply_context or '(not a reply or no reply text available)'}\n\n"
        "Current message to classify:\n"
        f"{current_message}\n\n"
        "Return the JSON decision now."
    )
    return system_prompt, user_prompt
