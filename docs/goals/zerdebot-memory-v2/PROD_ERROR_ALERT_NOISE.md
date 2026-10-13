# Production Bot error notification noise

以下至“生产 Bot 告警降噪已发布”之前为实施前冻结计划；`Current Behavior` 描述当时旧策略。当前已部署结果见文末发布证据。

**Intent:** Stop repeated administrator fault/recovery messages while retaining useful sustained-failure alerts.
**Current Behavior:** The production Bot Errors alarm uses Sum >= 1 in one 300-second period. Both ALARM and recovery OK reach the private administrator. Delivery timestamp deduplication does not merge different transitions. Fresh Oct13 readback found 21 ALARM and 21 OK transitions over the preceding day; the reported local 18:56/19:08 pair matches CloudWatch. Five failures in 13:45–14:22 UTC are Groq spam HTTP 413, not proof of a whole-Bot outage. Provider response bodies are intentionally absent, so the precise provider limit remains unknown.
**Expected Outcome:** This exact production Bot alarm requires all three consecutive five-minute periods to contain an error using `FILL(errors, 0)` with an explicit Sum/300-second metric before alerting. Its recovery OK is silently acknowledged in the same stream watermark, without claiming a delivery. Successfully delivered notifications for this stream start a one-hour cooldown; newer transitions during that cooldown are acknowledged as suppressed and cannot replay later as fresh incidents. Other alarms and budget notifications keep their current behavior.
**Target-Perspective Output:** One private message identifying sustained Bot request errors and the one-hour merge policy, rather than repeated ambiguous fault/recovery pairs. No test message is sent to the administrator.
**Truth Owner:** CloudWatch owns error evaluation; Operations owns parsing, private delivery and per-stream state in existing `operations#` keys. No new scheduler, table or notification sender.
**Contract Boundary:** Only `zerde-serverless-bot-prod-errors` gets the policy. Keep account/topic/ARN/time/private-recipient validation, the 90-second lease, failures visible and unknown-send semantics. A confirmed-send cooldown is not a cross-service exactly-once promise.
**Cutover:** Review and test source, CI, then serial dev and prod Operations releases. Prod alone changes its Bot error alarm. Protect every other function, layer, configuration, queue, table, model/cost owner and alarm. A narrow reviewed changeset must contain only Operations code (dev) or Operations code plus this alarm (prod). No direct manual business invocation or synthetic Telegram send. Actual package readback and independent offline replay prove delivery decisions; naturally occurring notification evidence is reported only if observed.
**Displaced Path:** Remove recovery messages and single-period fault notifications for this one stream. Existing raw metrics/history remain available.
**Value Density:** One alarm and its existing notifier, no project-wide alert redesign.
**Acceptance Evidence:** Exact synthetic state sequences for isolated error, sustained error, recovery, rapid re-alarm, one-hour boundary, duplicate/out-of-order suppressed events, concurrent lease, send/confirm failure and legacy rows; all unrelated alarm/budget behavior preserved. Real SDK/Moto conditional writes, targeted/full tests, hooks, CDK dev diff/prod assertions, actual ARM Operations artifact, bounded deployed code/config/alarm comparison and independent verification.
**Evidence Lane:** Synthetic delivery-policy verification and actual infrastructure/package readback. No claim of repaired Groq 413, real Telegram receipt or natural Memory acceptance.
**Kill Criteria:** Drift, unknown write outcome, extra changeset resources, changed protected packages or missing evidence stops execution. Preserve partial evidence; do not repeat a once deployment. Restore only through a separately reviewed exact rollback if necessary.
**Architecture Slice:** `infra/components/observability.py`, `infra/stack.py`, `src/operations/{main,operations_notifications,operations_state}.py`, relevant tests and current documentation. Avoid Bot/MemoryWorker business source, Groq policies, budget readers and frozen acceptance tools.
**Plan Review Gate:** Independent correctness and maintenance PRE before implementation; release tooling requires a separate exact PRE before any cloud write.

## State contract

Add a cooldown duration to the trusted parsed Notice, default zero. Only the exact production Bot error ALARM uses 3600 seconds; its OK becomes a trusted silent notice after the usual identity/time validation. The entrypoint claims the same stream lease and advances only `handled_at` for this silent recovery. This fences older delayed ALARM events after a known recovery, without starting/resetting cooldown. Other faults/recoveries and budget streams remain zero.

The existing repository claim still atomically acquires a lease and rejects both old delivered timestamps and new handled timestamps. Return the acquired row with the conditional update. During cooldown, under that lease, advance only `handled_at` and release; do not invent a delivery. Confirmed successful sends set `delivered_at`, `handled_at`, and a wall-clock `last_sent_at` (milliseconds), fenced by lease owner. For pre-upgrade rows with no wall-clock field, use their `delivered_at` conservatively as the cooldown anchor. Cooldown uses processing-clock milliseconds, allows a new send at elapsed >= 3600000, and is transition throttling rather than a scheduled hourly reminder. A failed send/confirmation must not advance the successful-send anchor. Same/older suppressed observations are subsequently ignored, including delayed duplicate deliveries. Failed suppression persistence remains a retryable error.

## Ordered work

1. Main: implement the narrow policy after PRE. Independent agents review; they do not implement product changes.
2. Main: run meaningful policy and infrastructure tests, full suite and hooks; resolve findings; publish source PR.
3. Main: prepare a bounded release contract/tools and original protected baseline. Review source/CI/changeset/artifacts independently. Deploy dev, verify/stabilize, then prod, verify/stabilize. Keep normal deploy workflow active and prevent a second publisher.
4. Main: synchronize actual plan/evidence/task_manifest/Z17 and Epic, and automation. Existing cleanup duties remain fixed. The new diagnostic/release raw batch started 2026-10-13 14:32:29.705948 UTC and expires 2026-10-20 14:32:29.705948 UTC (1792506749.705948); register all raw API/log/config/template derivatives at this same deadline. Pure source, complete ZIP and safe aggregates are retained. Do not extend old S snapshot deadlines or reuse old labels/readers as new permission.

User selected “仅持续故障提醒，并合并反复通知” on Oct13. No new approval is needed for the scoped repair/review/CI/merge/deployment already authorized. Media still needs its separate human exclusive-window confirmation. Production memory remains disabled, natural sample counts unchanged, and tonight's exact four-file cleanup remains due at 18:26:43.519150 UTC.


## 2026-10-13：生产 Bot 告警降噪已发布

用户选择仅持续故障提醒并合并反复通知。生产 Bot 错误告警现为连续三个5分钟窗口各有至少1次 Errors（缺失窗口填0）；同类私聊一小时内合并，恢复事件只推进处理水位、不再发恢复私聊。其他告警保持原策略。旧24小时42次状态转换不是42次已证明送达；本次有限日志窗口对应5次 Groq 垃圾检测 HTTP413，具体供应商限制仍UNKNOWN，本次没有修复该业务错误。

两环境各一次Execute完成，主/独立均下载五函数与共享层完整ZIP并核配置/模板/18告警，各已通过至少300秒稳定门禁。仅Operations三份Python更新，运行构建源 `f049f6856f990c8ec2d997558f1c4d482a1dbca9`；Bot/Memory仍PR257，News/Quiz/共享层和PR251身份配置保护保持。prod另改一条错误告警，dev告警未改。生产原prepare已上传并创建CS后被范围门禁拦截：旧候选漏告警标签、两条旧Quiz描述的CF读回为问号而Events现役为连接号；旧CS本轮未执行，失败保全。新候选仅恢复原标签和两现役描述，ZIP/ARM不重建，另新模板上传和CS后，原检查又因CF Context将五个布尔/整数字段表示成字符串而停止，第二次失败同样保全；新窄合同仅作精确同值类型核对，通过只读接续同一已创建CS，没有第三次上传或Create。实际规则日程/目标/全部标签经主独读回保持，描述表示差异原因UNKNOWN。首次生产post另因API空Dimensions表示差异在17只读后停止，未下载；新精确空数组合同完成只读主独续接，失败保全，没有再次部署。实际云写共10次，不能沿旧8次断言。74定向/2475全测、源码CI三个job及候选实际ARM/离线独审通过；原工具草稿问题和本地CDK schema预览失败保全，续接只换最小清单schema并引用原候选。另有实际偏差：dev栈DisableRollback由true变false，独审发现后保留原失败报告，并按新窄合同记录接受；原因UNKNOWN，不称该选项保持或已验证故障回滚。prod唯一Execute显式指定true，主独及稳定读回保持true。文档提交不是新运行构建，不重复部署。

本次新原文账本实际341份CAPTURED，统一原期限2026-10-20 14:32:29.705948UTC，不延长；加原八项共九项。最近Oct13 18:26:43.519150失败4仍单独到期；所有旧完成清理不重删重建。新Operations包使旧S/Z完整发布聚合绑定失效，未来预算/相册行动前须另窄重绑独审；reader源码未改变，没有取得新模型许可或Telegram独占窗口。操作者本轮未操作UI/调用模型，自然0/50有据0/20未知、production_ready=false，20任务14OPEN/6CLOSED、Epic OPEN保持。

[实际发布证据](evidence/2026-10-13-prod-alert-noise/release.safe.json)；[dev独立读回](evidence/2026-10-13-prod-alert-noise/post-independent-dev.safe.json)；[prod独立读回](evidence/2026-10-13-prod-alert-noise/post-independent-prod.safe.json)；[保留台账](RETAINED_COPIES.md)。
