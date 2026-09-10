"""Telegram syntax and live authorization for the single V2 control service."""

import asyncio
import html
import time
from dataclasses import replace

from .command_receipts import CommandReceipt
from .commands import MemoryCommandService
from .lifecycle import MemoryLifecycle
from .models import MemoryConflict, MemoryInputError, MemoryUnavailable
from .public_answers import MemoryPublicRetryRequiredError, try_memory_answer
from .telegram_ingestion import source_event

_TEXT = {
    "en": {
        "usage": (
            "/memory about me|group [page]\n/memory correct &lt;fact@version&gt; &lt;valu"
            "e&gt;\n/memory wrong &lt;fact@version&gt;\n/memory group confirm rule|decisio"
            "n &lt;value&gt;\n/memory forget me|this|group\n/memory optout|optin|status\nGr"
            "oup administrators: /memory on|off (learning only)."
        ),
        "done": "Memory operation completed: {state}.",
        "pending": (
            "Recording is fenced off for this deletion. Erasure is still pending; /memor"
            "y status shows progress. This is not a completed-deletion acknowledgement."
        ),
        "unavailable": "Memory V2 is not active or this operation is unavailable. No legacy memory is used.",
        "denied": "This operation requires current group membership; group changes require a group administrator.",
        "conflict": "The selected memory changed. Show the current profile and use its current fact reference.",
        "status": "Memory: {state}; learning: {learning}; your opt-out: {optout}; pending deletion: {pending}.",
    },
    "ru": {
        "usage": (
            "/memory about me|group [page]\n/memory correct &lt;fact@version&gt; &lt;valu"
            "e&gt;\n/memory wrong &lt;fact@version&gt;\n/memory group confirm rule|decisio"
            "n &lt;value&gt;\n/memory forget me|this|group\n/memory optout|optin|status\nАд"
            "министраторам: /memory on|off (только обучение)."
        ),
        "done": "Операция с памятью завершена: {state}.",
        "pending": (
            "Запись для удаляемых данных остановлена. Удаление ещё выполняется; проверьт"
            "е /memory status. Полное удаление пока не подтверждено."
        ),
        "unavailable": "Memory V2 не активна или операция недоступна. Старая память не используется.",
        "denied": "Нужно действующее членство в группе; изменения группы доступны администраторам.",
        "conflict": "Запись изменилась. Покажите текущий профиль и используйте актуальную ссылку на факт.",
        "status": "Память: {state}; обучение: {learning}; ваш отказ: {optout}; удаление ожидает: {pending}.",
    },
    "kk": {
        "usage": (
            "/memory about me|group [page]\n/memory correct &lt;fact@version&gt; &lt;valu"
            "e&gt;\n/memory wrong &lt;fact@version&gt;\n/memory group confirm rule|decisio"
            "n &lt;value&gt;\n/memory forget me|this|group\n/memory optout|optin|status\nӘк"
            "імшілерге: /memory on|off (тек үйрену)."
        ),
        "done": "Жад әрекеті аяқталды: {state}.",
        "pending": (
            "Өшірілетін деректерге жазу тоқтатылды. Өшіру әлі жүріп жатыр; /memory statu"
            "s арқылы тексеріңіз. Толық өшіру әзірге расталмады."
        ),
        "unavailable": "Memory V2 қосылмаған немесе әрекет қолжетімсіз. Ескі жад қолданылмайды.",
        "denied": "Топтың қазіргі мүшесі болу қажет; топ өзгерістерін әкімші растайды.",
        "conflict": "Дерек өзгерді. Қазіргі профильді ашып, фактінің жаңа сілтемесін пайдаланыңыз.",
        "status": "Жад: {state}; үйрену: {learning}; сіздің бас тартуыңыз: {optout}; өшіру күтуде: {pending}.",
    },
    "zh": {
        "usage": (
            "/memory about me|group [页码]\n/memory correct &lt;fact@version&gt; &lt;新值&gt;"
            "\n/memory wrong &lt;fact@version&gt;\n/memory group confirm rule|decision &lt"
            ";内容&gt;\n/memory forget me|this|group\n/memory optout|optin|status\n群管理员：/memo"
            "ry on|off（仅控制学习）。"
        ),
        "done": "记忆操作已完成：{state}。",
        "pending": "本次删除范围已停止写入，清理仍在进行。请通过 /memory status 查看进度；此消息不代表已经删除完成。",
        "unavailable": "Memory V2 尚未启用，或本次操作不可用。不会使用旧记忆。",
        "denied": "需要当前群成员身份；群级修改需要群管理员身份。",
        "conflict": "所选事实已发生变化，请显示当前档案并使用最新事实引用。",
        "status": "记忆：{state}；学习：{learning}；你的退出状态：{optout}；待完成删除：{pending}。",
    },
}


def text(key, lang, **values):
    return _TEXT.get(lang, _TEXT["en"])[key].format(**{k: html.escape(str(v)) for k, v in values.items()})


def fact_reference(value):
    try:
        fact_id, version = value.rsplit("@", 1)
        if not version.isdigit():
            raise ValueError
        return {"fact_id": fact_id, "fact_version": int(version)}
    except (AttributeError, ValueError):
        raise MemoryInputError("A versioned fact reference is required") from None


async def execute(ctx, repo, api):
    parts = ctx.text.split(maxsplit=1)
    args = parts[1].strip() if len(parts) == 2 else ""
    words = args.split()
    if not words:
        return text("usage", ctx.lang_code)
    admin = (
        args in {"on", "off", "forget group"}
        or args.startswith("group confirm ")
        or (words[0] in {"wrong", "correct"} and len(words) >= 2 and words[1].startswith("FACT#GROUP#"))
    )
    if not await api.authorize(ctx.chat_id, ctx.user_id, require_admin=admin):
        return text("denied", ctx.lang_code)
    checked_at = time.monotonic()

    # The domain has no network capability; this certificate is only this live call.
    def authorized(chat, actor, *, require_admin=False):
        return (
            str(chat) == str(ctx.chat_id)
            and str(actor) == str(ctx.user_id)
            and time.monotonic() - checked_at < 20
            and (not require_admin or admin)
        )

    if args == "status":
        control = repo.get_control(ctx.chat_id)
        subject = repo.get_subject(ctx.chat_id, ctx.user_id)
        pending = any(row.get("state") != "DONE" for row in repo._list(ctx.chat_id, "PURGE#"))
        return text(
            "status",
            ctx.lang_code,
            state=control["state"],
            learning=bool(control["learning_enabled"]),
            optout=bool(subject.get("optout")),
            pending=pending,
        )
    action, ref = None, None
    if args in {"on", "off", "forget me", "forget group", "forget this", "optout", "optin"}:
        action = args.replace(" ", "_")
    elif words[0] in {"wrong", "correct"} and (len(words) == 2 if words[0] == "wrong" else len(words) >= 3):
        action, ref = words[0], fact_reference(words[1])
    elif words[:2] == ["group", "confirm"] and len(words) >= 4:
        action = "confirm_group"
    if action is None:
        return text("usage", ctx.lang_code)
    target = (ctx.reply_to_message or {}).get("message_id") if action == "forget_this" else None
    receipt = CommandReceipt(repo, ctx, action, fact_ref=ref, target_source=target)
    receipt.acquire()
    try:
        result = receipt.recover()
        if result is None:
            scoped = receipt.fenced_repo
            commands = MemoryCommandService(scoped, MemoryLifecycle(scoped), authorize=authorized)
            if action in {"on", "off"}:
                if not authorized(ctx.chat_id, ctx.user_id, require_admin=True):
                    raise MemoryUnavailable("Live administrator authorization expired")
                control = scoped.get_control(ctx.chat_id)
                # Initial cutover is operator-gated. Group-forget may restart cleanly.
                if action == "on" and control["state"] == "STOPPED" and control.get("purged_through"):
                    scoped.activate_group(ctx.chat_id, expected_revision=int(control["revision"]))
                else:
                    scoped.set_learning_enabled(ctx.chat_id, action == "on", expected_revision=int(control["revision"]))
                result = {"state": "LEARNING_ON" if action == "on" else "LEARNING_OFF"}
            elif action == "forget_me":
                result = commands.forget_me(ctx.chat_id, ctx.user_id)
            elif action == "optout":
                result = commands.optout(ctx.chat_id, ctx.user_id)
            elif action == "optin":
                result = commands.optin(ctx.chat_id, ctx.user_id)
            elif action == "forget_group":
                result = commands.forget_group(ctx.chat_id, ctx.user_id)
            elif action == "forget_this":
                result = commands.forget_source(ctx.chat_id, ctx.user_id, target)
            elif action == "wrong":
                result = commands.wrong(ctx.chat_id, ctx.user_id, ref)
            elif action == "correct":
                value = args.split(maxsplit=2)[2]
                source = replace(source_event(ctx._update), source_kind="confirmation")
                result = commands.correct(ctx.chat_id, ctx.user_id, ref, source_event=source, value=value)
            else:
                _, _, field, value = args.split(maxsplit=3)
                source = replace(source_event(ctx._update), source_kind="confirmation")
                result = commands.confirm_group(ctx.chat_id, ctx.user_id, source_event=source, field=field, value=value)
            result = receipt.complete(result)
    finally:
        receipt.release()
    if result.get("kind") == "PURGE":
        result = MemoryLifecycle(repo).advance(ctx.chat_id, result["sk"], max_pages=2)
        if result["state"] != "DONE":
            return text("pending", ctx.lang_code)
    return text("done", ctx.lang_code, state=result["state"])


def handle_memory_v2(ctx):
    from core.config import get_bot_token, is_configured_group_chat

    from .runtime import get_memory_v2_repo
    from .telegram_api import MemoryTelegramAPI

    repo = get_memory_v2_repo()
    if repo is None:
        ctx.reply(text("unavailable", ctx.lang_code), ctx.message_id)
        return
    words = ctx.text.split()
    if len(words) in {3, 4} and words[1] == "about" and words[2] in {"me", "group"}:
        try:
            page = int(words[3]) - 1 if len(words) == 4 else 0
            handled = try_memory_answer(
                ctx.message, question="profile", lang=ctx.lang_code, about=True, group=words[2] == "group", page=page
            )
            if not handled:
                ctx.reply(text("unavailable", ctx.lang_code), ctx.message_id)
        except (ValueError, MemoryInputError):
            ctx.reply(text("usage", ctx.lang_code), ctx.message_id)
        return
    api = MemoryTelegramAPI(get_bot_token(), configured=is_configured_group_chat)
    try:
        result = asyncio.run(execute(ctx, repo, api))
    except MemoryConflict:
        result = text("conflict", ctx.lang_code)
    except (MemoryInputError, ValueError, TypeError):
        result = text("usage", ctx.lang_code)
    except MemoryUnavailable:
        result = text("unavailable", ctx.lang_code)
    except Exception:
        raise MemoryPublicRetryRequiredError("Memory control state requires redelivery") from None
    # This acknowledgement contains no fact/private body. Unknown send is not retried.
    try:
        asyncio.run(api.send(ctx.chat_id, result, reply_to_message_id=ctx.message_id))
    except MemoryUnavailable:
        return
