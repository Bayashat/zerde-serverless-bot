"""Conservative field postcondition for clear, single personal education questions.

This does not identify people, infer qualifications or parse arbitrary language.
Only complete simple questions match. Quotes, multiple clauses and unfamiliar
wording keep the ordinary selector path; the corpus/gold is never an input.
"""

import re
import unicodedata

_EN_PERSON = r"(?:i|you|he|she|they|this (?:person|member|participant|user))"
_RU_PERSON = r"(?:я|ты|вы|он|она|они|этот участник|эта участница)"
_KK_PERSON = r"(?:ол|мен|сіз|сен|(?:бұл|осы) (?:қатысушы|адам|мүше|участник))"
_ZH_PERSON = r"(?:我|你|他|她|这位成员|这个人|该成员)"
_EDUCATION_QUESTIONS = tuple(
    re.compile(pattern)
    for pattern in (
        rf"(?:what|which) (?:degree|qualification) (?:do|does|did) {_EN_PERSON} "
        r"(?:have|hold|earn|complete|say (?:i|you|he|she|they) (?:earned|completed))",
        rf"(?:what|which) (?:major|degree) did {_EN_PERSON} "
        r"(?:study|complete|graduate with|say (?:i|you|he|she|they) (?:studied|completed))",
        rf"(?:what|which) (?:subject|field) did {_EN_PERSON} study at (?:university|college|school)",
        rf"по какой специальности {_RU_PERSON} (?:учился|училась|учились|окончил вуз|окончила вуз)",
        r"какое образование у (?:меня|тебя|вас|него|неё|нее|них|этого участника|этой участницы)",
        rf"{_KK_PERSON} (?:өзі )?(?:қандай|қай|какой) мамандық "
        r"(?:оқығанын айтты|бойынша (?:білім алған|оқыған)|оқыған)",
        rf"{_KK_PERSON} (?:университетте|колледжде) нені оқыған",
        r"(?:оның|менің|сіздің|осы қатысушының) дипломы қандай салада",
        rf"{_ZH_PERSON}(?:读的是什么专业|学的是什么专业|是什么学历|提过自己的学历吗)",
    )
)


def education_only_question(question: str) -> bool:
    if not isinstance(question, str) or not 0 < len(question) <= 4000:
        return False
    # Do not turn translations, quoted examples, multi-question or multi-topic
    # requests into an education-only request by extracting a matching substring.
    text = unicodedata.normalize("NFKC", question).casefold().strip()
    if any(char in text for char in ('"', "'", "“", "”", "«", "»", "`", "\n", "\r")):
        return False
    if text.endswith(("?", "？")):
        text = text[:-1].rstrip()
    text = " ".join(text.split())
    return any(pattern.fullmatch(text) for pattern in _EDUCATION_QUESTIONS)


def constrain_education_selection(question, facts, mode, indices):
    """A semantic rejection is a normal unknown, not another paid attempt.

    The selector already owns schema/index validation. Keep original indices and
    the whole selection: never salvage a mixed answer by silently dropping facts.
    """
    if education_only_question(question) and (
        mode == "general" or mode == "facts" and any(facts[index]["field"] != "education" for index in indices)
    ):
        return "unknown", ()
    return mode, indices
