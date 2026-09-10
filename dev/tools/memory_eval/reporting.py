"""Human-readable outputs keep metric denominators and evidence limits visible."""

import json
from pathlib import Path


def _percent(value):
    return "无分母 / 未验证" if value is None else f"{value:.2%}"


def render_report(report):
    lines = [
        "# Memory V2 离线评估",
        "",
        "**产品状态：IMPLEMENTED_UNPROVEN；模型效果：NOT_VERIFIED。**",
        "",
        f"观测来源：`{report['provenance'].get('provider_kind')}`。本报告不能替代真实模型 trace、独立标签复核、dev canary 或七天真实群试运行。",
        "",
        (
            f"语料：{report['corpus']['totals']['scenarios']} 场景 / "
            f"{report['corpus']['totals']['gold_facts']} 唯一 gold 事实标注 / "
            f"{report['corpus']['totals']['unknown_questions']} 未知问题。"
        ),
        f"语料 SHA256：`{report['corpus']['sha256']}`。全部文本、身份和业务快照均为合成、AI 编写。",
        "",
        "| 切片 | TP / FP / FN | Precision | Recall | 来源支持（支持/断言） | Unknown abstention（正确/问题） |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for label, row in [("总计", report["overall"]), *report["languages"].items()]:
        lines.append(
            f"| {label} | {row['tp']} / {row['fp']} / {row['fn']} | "
            f"{_percent(row['precision'])} | {_percent(row['recall'])} | "
            f"{_percent(row['source_support'])} ({row['supported_assertions']}/{row['assertions']}) | "
            f"{_percent(row['unknown_abstention'])} ({row['unknown_abstained']}/{row['unknown_questions']}) |"
        )
    lines += ["", "已知问题完整回答比例逐语言必须 ≥90%；不能用未知拒答率代表正常问答能力：", ""]
    for label, row in report["languages"].items():
        lines.append(
            f"- {label}: {_percent(row['supported_answer_recall'])} "
            f"({row['supported_answers_complete']}/{row['supported_questions']})。"
        )
    lines += ["", "零容忍各自判定，缺 trace 是 UNVERIFIED，不能计作零错误：", ""]
    for gate, row in report["zero_tolerance"].items():
        lines.append(
            f"- {gate}: {row['status']}；错误 {row['count']}，可检查 checkpoint {row['verified_checkpoints']}。"
        )
    lines += [
        "",
        f"数值门槛满足：{report['numeric_thresholds_pass']}；观测完整：{report['complete']}。这只描述所提供文件，不认证其真实模型来源。",
        "",
        "正常处理、恢复、暂停与过期分别报告；暂停/过期不会当作 DONE 或零延迟：",
        "",
        "```json",
        json.dumps(
            {"coverage": report["coverage"], "latency": report["latency"], "cost": report["cost"]},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "dev canary：NOT_RUN。真实群：0 天 / 0 有依据问答 / 0 未知问题；门槛为 7 天 / 50 / 20。",
        "",
    ]
    return "\n".join(lines)


def render_catalog(corpus):
    lines = [
        "# Memory V2 合成语料目录",
        "",
        "AI 编写，非真实群聊天；独立复核状态单列。每个 checkpoint 明确有效事实及必须拒绝的未知问题。",
        "",
    ]
    for scenario in corpus:
        lines += [
            f"## {scenario['scenario_id']} · {scenario['language']} · {scenario['title']}",
            "",
            f"标签：{', '.join(scenario['tags'])}；独立复核：{scenario['independent_review']}。",
            "",
        ]
        for event in scenario["events"]:
            lines.append(
                f"- `{event['event_id']}` {event['type']} · chat `{event.get('chat_id', '-')}`"
                f" / author `{event.get('user_id', '-')}`：{event.get('text') or event.get('detail', '')}"
            )
        for checkpoint in scenario["checkpoints"]:
            lines += ["", f"Checkpoint `{checkpoint['checkpoint_id']}`（{checkpoint['after_event']} 后）：", ""]
            for fact in checkpoint["facts"]:
                evidence = fact["evidence"]
                lines.append(
                    f"- `{fact['fact_id']}` {fact['subject_id']}"
                    f" / {fact['field']} / {fact['facet'] or '-'} = **{fact['value']}**；"
                    f"证据 `{evidence['source_event']}[{evidence['start']}:{evidence['end']}]`。"
                )
            if not checkpoint["facts"]:
                lines.append("- 有效事实应为空。")
            for question in checkpoint.get("questions", []):
                lines.append(f"- 问 `{question['question_id']}`：{question['text']} → **{question['expected']}**。")
        lines.append("")
    return "\n".join(lines)


def write_report(report, output):
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (directory / "report.md").write_text(render_report(report))
