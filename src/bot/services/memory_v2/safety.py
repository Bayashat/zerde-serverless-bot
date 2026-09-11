"""Shared final public-content policy for V2 ingestion/extraction/fact commits.

This is a deterministic rejection layer, not a semantic proof of consent or
self-attribution. Z07 still validates explicit self claims and multilingual evals.
"""

import re
import unicodedata

from services.memory_safety import is_memory_learning_safe

from .models import MemoryInputError

_SECRET_OR_PRIVATE = re.compile(
    r"(?:password|passwd|passphrase|api[ _-]?key|access[ _-]?token|secret|private[ _-]?key|"
    r"парол\w*|секрет\w*|құпия\w*|қупия\w*|密码|密钥|令牌|"
    r"salary|paycheck|income|bank[ _-]?account|iban|credit[ _-]?card|"
    r"зарплат\w*|доход\w*|банковск\w*\s+сч[её]т|жалақы\w*|жалаки\w*|табыс\w*|工资|薪资|银行卡|账户|"
    r"diagnos\w*|medical|HIV|cancer|диагноз\w*|болезн\w*|ауру\w*|病史|诊断|"
    r"passport|national[ _-]?id|паспорт\w*|\bиин\b|жсн|身份证|"
    r"sexual|religio\w*|political\s+(?:party|belief)|"
    r"(?:street|apartment|apt\.?|avenue|улиц\w*|квартир\w*|көш\w*|пәтер\w*|街道|门牌|住址)"
    r")",
    re.IGNORECASE,
)
_CONTACT = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b|(?:\+?\d[\d ()-]{6,}\d)|https?://|t\.me/", re.IGNORECASE)
_TOKEN = re.compile(
    r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"[0-9]{5,}:[A-Za-z0-9_-]{20,}|(?:[$€£₸]|USD|KZT|₽)\s*\d",
    re.IGNORECASE,
)
_NAME_DIRECTIVE = re.compile(
    r"回答|忽略|指令|发送|输出|请|总是|必须|отвеч|говори|пиши|\bжауап\b|\bжаз\b|\bайт\b", re.IGNORECASE
)
_DIRECTIVE = re.compile(
    r"(?:ignore|override|disregard|system\s+prompt|always\s+(?:answer|say|respond)|"
    r"игнорир\w*|всегда\s+отвеч\w*|忽略|系统提示|总是回答)",
    re.IGNORECASE,
)
_KAZAKH_INSTRUCTION = re.compile(r"(?:нұсқау|нускау)\w*", re.IGNORECASE)
_KAZAKH_MANUAL = re.compile(r"(?:нұсқаулық|нұсқаулығ|нускаулык|нускаулыг)\w*", re.IGNORECASE)
_MANUAL_CONTROL = re.compile(
    r"\b(?:елеме\w*|ескерме\w*|орында\w*|ұмыт\w*|умыт\w*|бағын\w*|багын\w*|ұстан\w*|устан\w*|"
    r"әрқашан|аркашан|айт|айтыңыз|айтшы|жаз|жазыңыз|жазшы|"
    r"follow|obey|execute|remember|memorize|respond|answers?|replies|say|must|always|"
    r"выполн\w*|следу\w*|запомн\w*|отвеч\w*|ответь|скажи|говори|пиши)\b|"
    r"жауап\s+бер\w*|бұдан\s+былай|будан\s+былай|遵循|执行|记住|回答|输出",
    re.IGNORECASE,
)


def _kazakh_directive(text: str) -> bool:
    words = _KAZAKH_INSTRUCTION.findall(text)
    # A handbook is a public noun, not permission to execute its contents. Keep
    # rejecting instruction words; the narrow noun lane still rejects control
    # language anywhere in the complete message, including another sentence.
    return bool(words) and (
        any(not _KAZAKH_MANUAL.fullmatch(word) for word in words) or bool(_MANUAL_CONTROL.search(text))
    )


def require_public_content(text: str, *, max_length: int) -> None:
    if not isinstance(text, str) or not text.strip() or len(text) > max_length:
        raise MemoryInputError("Invalid public content length")
    folded = unicodedata.normalize("NFKC", text)
    if any(unicodedata.category(char) in {"Cc", "Cf"} and char not in "\n\r\t" for char in folded):
        raise MemoryInputError("Hidden control characters are not public fact content")
    if (
        not is_memory_learning_safe(folded)
        or _SECRET_OR_PRIVATE.search(folded)
        or _CONTACT.search(folded)
        or _DIRECTIVE.search(folded)
        or _kazakh_directive(folded)
        or _TOKEN.search(folded)
    ):
        raise MemoryInputError("Content is not eligible for public memory")


def require_preference_name(value: str) -> None:
    if _NAME_DIRECTIVE.search(value):
        raise MemoryInputError("Preferred name cannot contain response instructions")
    if len(value) > 40 or any(not (char.isalpha() or char in " -'") for char in value):
        raise MemoryInputError("Preferred name must be a short name, not instructions")
    if any(
        word.casefold()
        in {"answer", "reply", "respond", "speak", "write", "say", "говори", "отвечай", "пиши", "жаз", "айт"}
        for word in value.split()
    ):
        raise MemoryInputError("Preferred name cannot contain response instructions")
    if len(value.split()) > 4:
        raise MemoryInputError("Preferred name is too long")
