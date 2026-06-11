# src/quiz/services/quiz_generator.py
"""IT quiz question generator with provider-agnostic LLM backend."""

import hashlib
import re
from statistics import mean

from core.logger import LoggerAdapter, get_logger
from services.llm_provider import QuizLLMProvider

logger = LoggerAdapter(get_logger(__name__), {})

_OPTION_MAX_LEN = 100
_QUESTION_MAX_LEN = 300
_OPTION_LENGTH_RATIO_MAX = 1.8

DIFFICULTY_POINTS: dict[str, int] = {
    "easy": 1,
    "easy_medium": 2,
    "medium": 3,
    "medium_hard": 4,
    "hard": 5,
    "expert": 5,
}

CATEGORY_POOL = [
    "programming",
    "ai",
    "cicd",
    "cloud",
    "containers",
    "cybersecurity",
    "data-structures",
    "database",
    "devops",
    "networking",
    "system-design",
]

SUBTOPIC_POOL: dict[str, list[str]] = {
    "programming": [
        "Python / GIL",
        "Python / async await",
        "JavaScript / event loop",
        "TypeScript / type narrowing",
        "Git / branching",
        "Linux / processes",
        "API design / idempotency",
        "testing / mocks",
    ],
    "ai": [
        "LLM / context window",
        "LLM / hallucination",
        "RAG / chunking",
        "embeddings / similarity",
        "prompting / constraints",
        "model evaluation / metrics",
        "agents / tool calling",
        "AI safety / data leakage",
    ],
    "cicd": [
        "GitHub Actions / caching",
        "CI / flaky tests",
        "CD / rollback",
        "artifacts / versioning",
        "secrets / rotation",
        "release strategy / blue green",
        "pipeline security / least privilege",
        "deployment gates / approvals",
    ],
    "cloud": [
        "IAM / policy evaluation",
        "S3 / lifecycle",
        "Lambda / cold start",
        "VPC / subnet routing",
        "CloudWatch / metrics",
        "DynamoDB / partition keys",
        "RDS / multi AZ",
        "cost / reserved capacity",
    ],
    "containers": [
        "Docker / layers",
        "Docker / multi-stage builds",
        "Kubernetes / probes",
        "Kubernetes / requests and limits",
        "Kubernetes / services",
        "Kubernetes / rolling updates",
        "container security / images",
        "orchestration / scheduling",
    ],
    "cybersecurity": [
        "authentication / MFA",
        "authorization / RBAC",
        "TLS / certificates",
        "OWASP / injection",
        "secrets / storage",
        "network security / firewalls",
        "logging / incident response",
        "cryptography / hashing",
    ],
    "data-structures": [
        "arrays / complexity",
        "hash maps / collisions",
        "trees / traversal",
        "graphs / shortest path",
        "heaps / priority queues",
        "queues / backpressure",
        "sets / membership",
        "tries / prefix search",
    ],
    "database": [
        "indexes / transactions",
        "SQL / joins",
        "isolation levels / anomalies",
        "replication / lag",
        "partitioning / hot keys",
        "query planning / scans",
        "NoSQL / access patterns",
        "backups / point-in-time recovery",
    ],
    "devops": [
        "observability / alerting",
        "infrastructure as code / drift",
        "incident response / rollback",
        "SLO / error budget",
        "configuration / environment parity",
        "logging / correlation IDs",
        "capacity planning / autoscaling",
        "runbooks / automation",
    ],
    "networking": [
        "DNS / TTL",
        "HTTP / caching",
        "TCP / retransmission",
        "TLS / handshake",
        "load balancing / health checks",
        "CIDR / subnetting",
        "NAT / outbound traffic",
        "CDN / cache invalidation",
    ],
    "system-design": [
        "caching / consistency",
        "queues / backpressure",
        "rate limiting / fairness",
        "sharding / hot partitions",
        "replication / failover",
        "idempotency / retries",
        "pagination / cursors",
        "eventual consistency / read models",
    ],
}


_LANG_NAMES = {
    "kk": "Kazakh (Cyrillic script)",
    "zh": "Simplified Chinese",
    "ru": "Russian",
}

_DIFFICULTY_DESCRIPTIONS = {
    "easy": "L1 foundation recall: one concrete term, command, service, or basic concept.",
    "easy_medium": "L2 foundation understanding: compare two close concepts or choose the best basic use case.",
    "medium": "L3 applied scenario: short realistic situation requiring reasoning, not a definition.",
    "medium_hard": "L4 troubleshooting/design: diagnose a failure mode, constraint, or trade-off.",
    "hard": "L5 advanced architecture: edge cases, scaling, security, consistency, or cost trade-offs.",
    "expert": "L5 advanced architecture: deep internals, subtle traps, and realistic production trade-offs.",
}


def question_fingerprint(question: str) -> str:
    """Return a stable low-cost fingerprint for exact-ish question dedupe."""
    normalized = re.sub(r"[^a-z0-9\s]+", " ", question.lower())
    normalized = re.sub(r"\b\d+\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _significant_terms(value: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9\s]+", " ", value.lower())
    return {
        term
        for term in normalized.split()
        if len(term) >= 4
        and term
        not in {
            "what",
            "which",
            "when",
            "where",
            "would",
            "should",
            "could",
            "with",
            "from",
            "that",
            "this",
            "then",
            "best",
            "most",
            "following",
        }
    }


class QuizGenerator:
    """Generates IT quiz questions via an injected LLM provider."""

    def __init__(self, provider: QuizLLMProvider) -> None:
        self._provider = provider
        logger.info("QuizGenerator initialized")

    def get_rpd_status(self) -> tuple[int | None, int | None]:
        """Return provider RPD status when available."""
        return self._provider.get_rpd_status()

    def generate_question(
        self,
        category: str,
        lang: str,
        difficulty: str = "easy",
        subtopic: str | None = None,
        interactive: bool = False,
    ) -> dict | None:
        """Generate a quiz question for the given category, language, and difficulty.

        Returns a dict with keys: question, options, correct_option_index, explanation,
        difficulty, points.
        Returns None if generation or validation fails.
        """
        lang_name = _LANG_NAMES.get(lang, lang)
        difficulty_description = _DIFFICULTY_DESCRIPTIONS.get(difficulty, _DIFFICULTY_DESCRIPTIONS["easy"])
        topic_path = f"{category} / {subtopic}" if subtopic else category
        prompt = (
            f"You are an IT quiz question writer for a developer community.\n"
            f"Generate exactly 1 multiple-choice IT quiz question about this topic path: {topic_path}.\n\n"
            "LANGUAGE RULES:\n"
            f"1. Write the question text, all 4 answer options, and the explanation entirely in {lang_name}.\n"
            "2. Keep well-known technical terms in English where natural "
            "(e.g. Python, Docker, AWS, SQL, HTML, CSS, Git, Linux, CI/CD, API).\n"
            "3. CRITICAL LENGTH CONSTRAINTS (hard Telegram API limits):\n"
            "   - Question text: at most 300 characters.\n"
            "   - Each option: at most 100 characters. Abbreviate aggressively if needed.\n"
            "   - Explanation: at most 200 characters.\n\n"
            "CONTENT RULES:\n"
            "4. Provide exactly 4 answer options.\n"
            "5. Exactly 1 option must be correct.\n"
            f"6. Difficulty target: {difficulty} — {difficulty_description}\n"
            "7. Avoid generic textbook-definition questions unless difficulty is easy.\n"
            "8. For L3-L5, use a specific scenario with a concrete constraint or symptom.\n"
            "9. Make distractors plausible and from the same technical domain.\n"
            "10. Stay tightly within the requested topic path; do not drift to a broader category.\n"
            "11. All 4 options must be similar in length, specificity, grammar, and style.\n"
            "12. The correct option must NOT be the longest or most detailed option.\n"
            "13. Do not reveal the answer in the question wording; avoid repeating the correct option's key phrase.\n\n"
            "Respond ONLY with a JSON object in this exact format:\n"
            '{"question": "...", "options": ["opt1", "opt2", "opt3", "opt4"], '
            '"correct_option_index": 0, "explanation": "..."}\n\n'
            "correct_option_index must be the 0-based index of the correct option in the options array."
        )

        try:
            data = self._provider.generate_json(prompt, temperature=0.3, interactive=interactive)
            return self._validate(data, category, lang, difficulty, subtopic)

        except Exception:
            logger.error(
                "Question generation failed",
                extra={"category": category, "lang": lang, "difficulty": difficulty},
                exc_info=True,
            )
            return None

    def translate_question(self, question: dict, lang: str, *, interactive: bool = False) -> dict | None:
        """Translate a banked (English) question dict into *lang*.

        Translates: question text, all 4 options, explanation.
        Non-text fields (correct_option_index, difficulty, points, source_label) are
        copied unchanged.

        Returns the translated dict on success, or None if translation/validation fails
        (caller should fall back to the original English question).
        """
        if lang == "en":
            return question

        lang_name = _LANG_NAMES.get(lang, lang)
        prompt = (
            f"Translate the following IT quiz question into {lang_name}.\n"
            "Rules:\n"
            "1. Keep well-known technical terms in English "
            "(e.g. AWS, S3, EC2, IAM, VPC, Docker, Kubernetes, Python, SQL, API, CLI).\n"
            "2. CRITICAL LENGTH LIMITS (hard Telegram API limits):\n"
            "   - question: at most 300 characters.\n"
            "   - Each option: at most 100 characters. Abbreviate aggressively if needed.\n"
            "   - explanation: at most 200 characters.\n"
            "3. Preserve the original meaning exactly — do NOT change the correct answer.\n"
            "4. Respond ONLY with a JSON object in this exact format:\n"
            '   {"question": "...", "options": ["opt1","opt2","opt3","opt4"], "explanation": "..."}\n\n'
            "Source question (English):\n"
            f"question: {question['question']}\n"
            f"options: {question['options']}\n"
            f"explanation: {question.get('explanation') or ''}"
        )

        try:
            data = self._provider.generate_json(prompt, temperature=0.1, interactive=interactive)
            if not isinstance(data, dict):
                logger.warning(
                    "Translation provider returned non-dict",
                    extra={"lang": lang, "type": type(data).__name__},
                )
                return None
            return self._validate_translation(data, question, lang)
        except Exception:
            logger.error(
                "Question translation failed",
                extra={"lang": lang},
                exc_info=True,
            )
            return None

    def _validate_translation(self, data: dict, original: dict, lang: str) -> dict | None:
        """Validate translated content and merge with non-text original fields."""
        q_text = (data.get("question") or "").strip()
        options = data.get("options", [])
        explanation = (data.get("explanation") or "").strip() or None

        if not q_text or len(q_text) > _QUESTION_MAX_LEN:
            logger.warning(
                "Translated question empty or too long",
                extra={"lang": lang, "length": len(q_text)},
            )
            return None

        if not isinstance(options, list) or len(options) != 4:
            logger.warning("Translated options count invalid", extra={"lang": lang})
            return None

        for i, opt in enumerate(options):
            if not isinstance(opt, str) or not opt.strip():
                logger.warning("Translated option empty", extra={"lang": lang, "index": i})
                return None
            if len(opt.strip()) > _OPTION_MAX_LEN:
                logger.warning(
                    "Translated option too long",
                    extra={"lang": lang, "index": i, "length": len(opt.strip())},
                )
                return None

        return {
            **original,
            "question": q_text,
            "options": [opt.strip() for opt in options],
            "explanation": explanation,
        }

    def _validate(
        self,
        data: dict,
        category: str,
        lang: str,
        difficulty: str = "easy",
        subtopic: str | None = None,
    ) -> dict | None:
        """Validate Gemini response shape and Telegram length limits."""
        question = (data.get("question") or "").strip()
        options = data.get("options", [])
        correct_index = data.get("correct_option_index")
        explanation = (data.get("explanation") or "").strip() or None

        if not question:
            logger.warning("Generated question is empty", extra={"category": category, "lang": lang})
            return None

        if len(question) > _QUESTION_MAX_LEN:
            logger.warning(
                "Generated question exceeds Telegram limit",
                extra={"length": len(question), "category": category, "lang": lang},
            )
            return None

        if not isinstance(options, list) or len(options) != 4:
            logger.warning(
                "Generated options count invalid",
                extra={"got": len(options) if isinstance(options, list) else "n/a", "category": category},
            )
            return None

        for i, opt in enumerate(options):
            if not isinstance(opt, str) or not opt.strip():
                logger.warning("Option is empty or non-string", extra={"index": i, "category": category})
                return None
            if len(opt.strip()) > _OPTION_MAX_LEN:
                logger.warning(
                    "Option exceeds Telegram limit",
                    extra={"index": i, "length": len(opt.strip()), "category": category},
                )
                return None

        stripped_options = [opt.strip() for opt in options]
        lengths = [len(opt) for opt in stripped_options]
        avg_length = mean(lengths)
        if avg_length and max(lengths) / avg_length > _OPTION_LENGTH_RATIO_MAX:
            logger.warning(
                "Generated options have obvious length imbalance",
                extra={"lengths": lengths, "category": category, "difficulty": difficulty},
            )
            return None

        if not isinstance(correct_index, int) or isinstance(correct_index, bool) or not (0 <= correct_index <= 3):
            logger.warning(
                "correct_option_index invalid",
                extra={"value": correct_index, "category": category},
            )
            return None

        correct_length = lengths[correct_index]
        if correct_length == max(lengths) and correct_length > avg_length * 1.35:
            logger.warning(
                "Correct option is conspicuously longer than distractors",
                extra={"lengths": lengths, "correct_index": correct_index, "category": category},
            )
            return None

        question_terms = _significant_terms(question)
        correct_terms = _significant_terms(stripped_options[correct_index])
        other_terms = set().union(
            *[_significant_terms(opt) for i, opt in enumerate(stripped_options) if i != correct_index]
        )
        leaked_terms = (question_terms & correct_terms) - other_terms
        if leaked_terms and len(leaked_terms) >= 2:
            logger.warning(
                "Question wording appears to leak correct answer terms",
                extra={"category": category, "leaked_terms": sorted(leaked_terms)[:5]},
            )
            return None

        return {
            "question": question,
            "options": stripped_options,
            "correct_option_index": correct_index,
            "explanation": explanation,
            "difficulty": difficulty,
            "points": DIFFICULTY_POINTS.get(difficulty, 1),
            "subtopic": subtopic,
            "fingerprint": question_fingerprint(question),
        }
