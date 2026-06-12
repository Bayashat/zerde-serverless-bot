"""Trust filters for memory and agent prompt context."""

from __future__ import annotations

import re

_SAFE_PHRASES_RE = re.compile(
    r"\b(?:best practices?|top[- ]?k|top[- ]?level|topology)\b",
    flags=re.IGNORECASE,
)

_SUBJECTIVE_RANKING_RE = re.compile(
    "|".join(
        (
            r"\bbest\b",
            r"\bstrongest\b",
            r"\bgreatest\b",
            r"\bgoat\b",
            r"\bnumber\s+one\b",
            r"\bno\.?\s*1\b",
            r"#\s*1\b",
            r"\btop\s*(?:1|one)?\b",
            r"\bлучши\w*\b",
            r"\bсам(?:ый|ая|ое|ые)\s+(?:лучш\w*|сильн\w*|крут\w*|опытн\w*)\b",
            r"\b(?:круче|лучше)\s+всех\b",
            r"\bномер\s+один\b",
            r"\bе[ңн]\s+(?:мықты|мыкты|күшті|кушти|үздік|уздик|жақсы|жаксы)\b",
            r"\b(?:мықты|мыкты|күшті|кушти)\s+(?:айтишник|айтушник|разраб|developer|dev|маман)\b",
            r"最(?:牛|牛逼|厉害|強|强|棒|优秀)",
            r"第一",
        )
    ),
    flags=re.IGNORECASE,
)

_PERSON_OR_GROUP_RE = re.compile(
    "|".join(
        (
            r"\bwho\b",
            r"\bperson\b",
            r"\bpeople\b",
            r"\bdeveloper\b",
            r"\bdev\b",
            r"\bengineer\b",
            r"\bprogrammer\b",
            r"\bchat\b",
            r"\bgroup\b",
            r"\bкто\b",
            r"\bчеловек\b",
            r"\bразраб\w*\b",
            r"\bразработчик\w*\b",
            r"\bпрограммист\w*\b",
            r"\bайтишник\w*\b",
            r"\bчат\w*\b",
            r"\bгрупп\w*\b",
            r"\bкім\b",
            r"\bадам\b",
            r"\bмаман\b",
            r"\bайтишник\b",
            r"\bчатта\b",
            r"\bтопта\b",
            r"谁",
            r"人",
            r"群",
            r"开发",
            r"程序员",
            r"工程师",
        )
    ),
    flags=re.IGNORECASE,
)

_QUESTION_CUE_RE = re.compile(r"\?|？|\bwho\b|\bкто\b|\bкім\b|谁", flags=re.IGNORECASE)

_FUTURE_ANSWER_DIRECTIVE_RE = re.compile(
    "|".join(
        (
            r"\b(?:from\s+now\s+on|going\s+forward|whenever|"
            r"when(?:ever)?\s+[^.!?\n]{0,80}\s+asks?|"
            r"if\s+[^.!?\n]{0,80}\s+asks?)\b"
            r"[^.!?\n]{0,160}\b(?:say|answer|reply|respond|tell|call)\b",
            r"\b(?:say|answer|reply|respond|tell|call)\b[^.!?\n]{0,120}"
            r"\b(?:if|when|whenever)\b[^.!?\n]{0,80}\b(?:ask|asks|asked)\b",
            r"\b(?:remember|memorize)\b[^.!?\n]{0,80}\b(?:as|that)\b",
            r"\b(?:если|когда)[^.!?\n]{0,120}(?:спрос|зада)[^.!?\n]{0,120}"
            r"(?:отвечай|ответь|скажи|говори|назови|называй)",
            r"\b(?:отвечай|ответь|скажи|говори|назови|называй)[^.!?\n]{0,120}"
            r"(?:если|когда)[^.!?\n]{0,120}(?:спрос|зада)",
            r"(?:десе|сұраса|сураса)[^.!?\n]{0,120}(?:деп\s+жауап\s+бер|жауап\s+бер|айт|дейсің)",
            r"(?:деп\s+жауап\s+бер|жауап\s+бер)[^.!?\n]{0,120}(?:десе|сұраса|сураса)",
            r"(?:以后|今后|如果[^。！？\n]{0,60}问|有人[^。！？\n]{0,60}问)[^。！？\n]{0,80}(?:回答|说|叫|称呼)",
            r"(?:回答|说|叫|称呼)[^。！？\n]{0,80}(?:如果[^。！？\n]{0,60}问|有人[^。！？\n]{0,60}问|以后|今后)",
        )
    ),
    flags=re.IGNORECASE,
)

_PROFILE_CONTEXT_NOISE_TERMS = {
    "best",
    "strongest",
    "top",
    "who",
    "chat",
    "group",
    "answer",
    "reply",
    "кто",
    "чат",
    "самый",
    "сам",
    "самыч",
    "лучший",
    "лучши",
    "отвечай",
    "ответь",
    "скажи",
    "кім",
    "ким",
    "чатта",
    "чаттағы",
    "топта",
    "ең",
    "ен",
    "енді",
    "енди",
    "мықты",
    "мыкты",
    "десе",
    "деп",
    "жауап",
    "бер",
    "айт",
    "мырза",
    "айтушник",
    "аитушник",
    "разраб",
    "хорошая",
    "девушка",
    "谁",
    "群",
    "最强",
    "最牛",
    "第一",
}


def _clean(text: str) -> str:
    return " ".join((text or "").split())


def _ranking_text(text: str) -> str:
    return _SAFE_PHRASES_RE.sub("", _clean(text))


def looks_like_future_answer_directive(text: str) -> bool:
    """Return True for attempts to install persistent future answer rules."""
    return bool(_FUTURE_ANSWER_DIRECTIVE_RE.search(_clean(text)))


def looks_like_subjective_ranking_claim(text: str) -> bool:
    """Return True for subjective ranking/superlative claims not safe for memory."""
    return bool(_SUBJECTIVE_RANKING_RE.search(_ranking_text(text)))


def looks_like_subjective_person_ranking_question(text: str) -> bool:
    """Return True for questions like "who is the best Go dev in this chat?"."""
    cleaned = _ranking_text(text)
    return bool(
        _SUBJECTIVE_RANKING_RE.search(cleaned)
        and _QUESTION_CUE_RE.search(cleaned)
        and _PERSON_OR_GROUP_RE.search(cleaned)
    )


def is_memory_learning_safe(text: str) -> bool:
    """Return False for prompt-injection-like rules and subjective rankings."""
    return not (looks_like_future_answer_directive(text) or looks_like_subjective_ranking_claim(text))


def is_profile_context_value_safe(text: str) -> bool:
    """Return False for profile fragments that should not be prompt context."""
    cleaned = _clean(text).lower().strip("@#.,:;!?()[]{}\"'")
    return bool(cleaned and cleaned not in _PROFILE_CONTEXT_NOISE_TERMS and is_memory_learning_safe(text))
