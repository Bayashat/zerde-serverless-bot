"""Deterministic personal/group assertions and clickable source evidence."""

import html
import re
from datetime import datetime, timezone

from .models import FRESHNESS_SECONDS, SINGLE_FIELDS, MemoryInputError
from .safety import require_public_content

_FIELDS = {
    "en": [
        "Occupation",
        "Current project",
        "City",
        "Education",
        "Technology",
        "Interest",
        "Communication preference",
        "Confirmed rule",
        "Confirmed decision",
    ],
    "ru": [
        "Работа",
        "Текущий проект",
        "Город",
        "Образование",
        "Технология",
        "Интерес",
        "Предпочтение в общении",
        "Подтверждённое правило",
        "Подтверждённое решение",
    ],
    "kk": [
        "Кәсібі",
        "Қазіргі жоба",
        "Қала",
        "Білімі",
        "Технология",
        "Қызығушылық",
        "Қарым-қатынас қалауы",
        "Расталған ереже",
        "Расталған шешім",
    ],
    "zh": ["职业", "当前项目", "城市", "教育", "技术栈", "兴趣", "沟通偏好", "已确认群规则", "已确认共同决定"],
}
_KEYS = [
    "occupation",
    "current_project",
    "location",
    "education",
    "tech_stack",
    "interests",
    "communication_preferences",
    "rule",
    "decision",
]
_TEXT = {
    "en": {
        "unknown": "I do not have a supported public self-statement for that.",
        "source": "Source",
        "no_link": "source link unavailable",
        "self": "Stated",
        "stale": "Last mentioned; not confirmed as current",
        "group": "Group",
        "member": "Member",
        "token": "Fact reference",
    },
    "ru": {
        "unknown": "У меня нет подтверждённого публичного высказывания самого участника об этом.",
        "source": "Источник",
        "no_link": "ссылка на источник недоступна",
        "self": "Сообщено",
        "stale": "Последнее упоминание; актуальность не подтверждена",
        "group": "Группа",
        "member": "Участник",
        "token": "Ссылка на факт",
    },
    "kk": {
        "unknown": "Бұл туралы адамның өзі айтқан, дәлелденген ашық мәлімет менде жоқ.",
        "source": "Дереккөз",
        "no_link": "дереккөз сілтемесі қолжетімсіз",
        "self": "Өзі айтқан",
        "stale": "Соңғы рет айтылған; қазір өзекті екені расталмаған",
        "group": "Топ",
        "member": "Қатысушы",
        "token": "Факт нөмірі",
    },
    "zh": {
        "unknown": "我没有找到本人明确公开说过、能支持这个问题的信息。",
        "source": "来源",
        "no_link": "来源链接不可用",
        "self": "明确提到",
        "stale": "上次提到，尚未确认现在仍成立",
        "group": "群",
        "member": "成员",
        "token": "事实编号",
    },
}


def source_link(chat_id, message_id):
    chat, message = str(chat_id), str(message_id)
    if re.fullmatch(r"-100[1-9][0-9]*", chat) and re.fullmatch(r"[1-9][0-9]*", message):
        return f"https://t.me/c/{chat[4:]}/{message}"
    return None


def unknown_text(lang):
    return _TEXT.get(lang, _TEXT["en"])["unknown"]


def render_facts(chat_id, facts, *, lang="en", subject_names=None, include_tokens=False, now=None):
    """Every value comes from a validated fact; dates and sources stay attached.

    The caller owns leases and MUST revalidate the complete selected reference set
    before each resulting message. Splitting never separates a claim from evidence.
    """
    labels = _TEXT.get(lang, _TEXT["en"])
    fields = dict(zip(_KEYS, _FIELDS.get(lang, _FIELDS["en"])))
    subject_names = subject_names or {}
    blocks = []
    for fact in facts:
        if str(fact["pk"]) != "CHAT#" + str(chat_id) or fact["field"] not in fields:
            raise MemoryInputError("Cannot render a fact outside this group")
        require_public_content(fact["value"], max_length=160)
        require_public_content(fact["evidence"]["excerpt"], max_length=240)
        subject = fact["subject_id"]
        name = subject_names.get(subject)
        if name is None:
            name = labels["group"] if subject == "GROUP" else labels["member"] + " " + subject.removeprefix("USER#")
        timestamp = datetime.fromtimestamp(int(fact["last_confirmed_at"]), timezone.utc).strftime("%Y-%m-%d UTC")
        stale = fact["freshness"] == "last_confirmed" or (
            now is not None
            and fact["field"] in SINGLE_FIELDS
            and now - int(fact["last_confirmed_at"]) >= FRESHNESS_SECONDS
        )
        qualifier = labels["stale"] if stale else labels["self"]
        ref = fact["evidence"]["source_ref"]
        link = source_link(chat_id, ref["source_id"])
        source = (
            f'<a href="{link}">{html.escape(labels["source"])}</a>'
            if link
            else html.escape(labels["no_link"] + " (#" + str(ref["source_id"]) + ")")
        )
        field = fields[fact["field"]]
        if fact.get("facet"):
            field += " / " + fact["facet"]
        block = (
            f'<b>{html.escape(str(name))} · {html.escape(field)}</b>: {html.escape(fact["value"])}\n'
            f"<i>{html.escape(qualifier)} · {timestamp}</i> · {source}\n"
            f'<blockquote>{html.escape(fact["evidence"]["excerpt"])}</blockquote>'
        )
        if include_tokens:
            token = fact["fact_id"] + "@" + str(fact["fact_version"])
            block += "\n" + html.escape(labels["token"]) + ": <code>" + html.escape(token) + "</code>"
        # Bound Telegram UTF-16 size conservatively by checking serialized HTML.
        if len(block.encode("utf-16-le")) // 2 > 3500:
            raise MemoryInputError("A fact block exceeds Telegram output bounds")
        blocks.append(block)
    messages, current = [], ""
    for block in blocks:
        proposed = current + ("\n\n" if current else "") + block
        if len(proposed.encode("utf-16-le")) // 2 > 3500:
            messages.append(current)
            current = block
        else:
            current = proposed
    if current:
        messages.append(current)
    return tuple(messages)


_TRENDS = {
    "en": (
        "Topics in a recent sample (seven-day window)",
        "messages",
        "participants",
        "Validated sample, not all group messages. Fixed technical topic dictionary; newer sources may be missing.",
        "Last inventory traversal",
        "not yet completed",
        "More profile facts",
    ),
    "ru": (
        "Темы недавней выборки (окно семь дней)",
        "сообщений",
        "участников",
        "Проверенная выборка, не все сообщения группы. Фиксированный словарь технических тем; "
        "новые источники могут отсутствовать.",
        "Последний обход источников",
        "ещё не завершён",
        "Другие факты профиля",
    ),
    "kk": (
        "Соңғы хабарламалар үлгісіндегі тақырыптар (жеті күн)",
        "хабарлама",
        "қатысушы",
        "Тексерілген үлгі, топтың барлық хабарламасы емес. Техникалық тақырыптар сөздігі "
        "шектеулі; жаңа деректер жетіспеуі мүмкін.",
        "Деректерді соңғы тексеру",
        "әлі аяқталмаған",
        "Профильдің келесі фактілері",
    ),
    "zh": (
        "近期样本话题（七天窗口）",
        "条消息",
        "位参与者",
        "这是已核验的样本，并非全群消息统计。使用固定技术话题词表，可能尚未包含新来源。",
        "上次遍历完成",
        "尚未完成",
        "更多档案事实",
    ),
}


def render_trends(view, lang):
    labels = _TRENDS.get(lang, _TRENDS["en"])
    snapshot = view.snapshot
    lines = ["<b>" + labels[0] + "</b>", html.escape(labels[3]), str(snapshot.eligible_source_count) + " " + labels[1]]
    for topic in snapshot.topics:
        refs = []
        for ref in topic.source_refs:
            link = source_link(snapshot.chat_id, ref.source_id)
            refs.append(f'<a href="{link}">#{ref.source_id}</a>' if link else "#" + ref.source_id)
        lines.append(
            html.escape(topic.topic.replace("_", " "))
            + ": "
            + str(topic.message_count)
            + " "
            + labels[1]
            + ", "
            + str(topic.participant_count)
            + " "
            + labels[2]
            + " · "
            + " ".join(refs)
        )
    completed = view.coverage["last_full_refresh_completed_at"]
    date = datetime.fromtimestamp(completed, timezone.utc).isoformat() if completed else labels[5]
    lines.append(labels[4] + ": " + date)
    lines.append(
        datetime.fromtimestamp(snapshot.window_started_at, timezone.utc).date().isoformat()
        + " → "
        + datetime.fromtimestamp(snapshot.as_of, timezone.utc).isoformat()
    )
    # Each topic carries its own complete bounded source list; never split claims.
    messages, current = [], ""
    for line in lines:
        proposed = current + ("\n" if current else "") + line
        if len(proposed.encode("utf-16-le")) // 2 > 3500:
            messages.append(current)
            current = line
        else:
            current = proposed
    if current:
        messages.append(current)
    return tuple(messages)


def pagination_text(lang, page, *, group=False):
    label = _TRENDS.get(lang, _TRENDS["en"])[6]
    return label + ": <code>/memory about " + ("group" if group else "me") + " " + str(page + 2) + "</code>"
