# Z13：Groq 413 的有限失败处理

## 状态与目标

2026-10-20，计划 PRE 后已完成本地实现及离线测试，正确性和维护独立 POST 已完成；尚未合并、发布或取得新的现场证据。用户要求在定时副本清理之外立即推进业务收尾；既有修复、独审、CI、合并和 dev/prod 发布授权保持。

Oct13 安全聚合记录有限窗口内五次 Groq 反垃圾 HTTP 413，具体账号限制仍 UNKNOWN。修复前本地 BASE 的 `groq_detector.py`、`processor.py`、SpamRepository 和 SQS router 与已发布 PR257 对应源码无差异（本轮尚未新读运行包）：413 产生普通 ProviderResponseError，case 无分类结果，worker 释放 lease 后失败，SQS 重投可能再次发送相同分类请求。不能把此次处理修复说成供应商限制已解除。

期望：明确收到 413 后，在原审核 case 内保留“未能分类”的事实，停止该 case 的重复模型请求并让管理员有机会审核；绝不由失败生成 CLEAN/SPAM 判断、学习许可、自动删除或封禁。

## 唯一所有权及范围

- 原 `SpamRepository` 的 stats `spam_case#decision#…`、input_hash/source_ref 和 lease 继续是唯一事实及并发 owner，不建新表、队列或扫描恢复入口。
- detector 在任何响应 body 解析之前仅对实际 HTTP 413 抛本地专用异常（继承 ProviderResponseError）；400 格式恢复、429、5xx、超时和其他消费者保持原规则。不按错误文案猜 413。
- 不改变模型、prompt、上下文截断、共享 SDK 配置、环境变量、预算 owner/计数或自动执行阈值。公开文档只确认 413 请求过大；本账号数值限制仍 UNKNOWN。
- 原 guest deterministic rule、captcha/admin 正常豁免及已完成审核保持；已持久化的 413 必须在管理员新豁免前恢复，不能因重投时身份变化自动变 CLEAN。

## 行为契约

1. 仅在新分类调用收到专用 413 异常时，持原 lease 写 `state=review`、`classifier_failure=groq_http_413`。不写 decision_label/confidence/reason 为分类结论。写失败继续失败，不能宣称持久化成功；无法跨 provider 与 DynamoDB 保证严格一次。
2. 重投在原 terminal/selected_action 防护后、admin finish_clean 前识别已存 failure，进入同一个审核分支，无模型、自动删除、封禁、CLEAN 或 outbox 创建。
3. 新通知用中性四语言文案：“自动检查未完成，请管理员检查原消息”，无 SPAM 断言或伪造置信度，不发送原文或 provider body。普通用户沿原 case 审核按钮；guest 仅真实正整数 personal caller 且非 bot 自身可成为审核目标。有 caller 的 guest 通知必须分别显示 bot 和 caller，并明确封禁按钮将永久封禁 caller、调用本身不证明恶意；无 caller 仅通知，无处罚按钮；服务端也拒绝该类 case 的 action，避免 callback fallback 指向 bot。
4. 新 413 通知使用 case 内 `provider_review_notice_state`：发送前写 ATTEMPTED，确认返回合法 message_id 后写 SENT 和 alert_sent；网络/返回/确认写不明保留 ATTEMPTED/UNKNOWN，不自动重发或捏造成功。下一队列重投返回 review，仍未批准学习。仅为 `TelegramClient.send_message` 增加默认保持原行为的可选 keyword，新的 413 通知显式传 `retries=False`，通过现有 `_post` 参数禁用本次隐藏 HTTP 重试；不修改共享 PoolManager 配置或其它发送调用。原非 413 通知流程不在本次改动范围；不声称全系统消息严格一次。持久化前的失败允许重试，因为尚未开始发送。
5. 原管理员身份、跨群、lease、selected_action、确认封禁计数和人工 ignore→CLEAN/source_ref outbox 继续生效。guest ignore 仍为 ignored，不进入 Memory。无 caller case 两种 action 均拒绝。
6. 仅新源码行为生效；不扫描、迁移、重投旧队列，不重做旧 Quiz/N-A-M-R/F5 等冻结验收。

通知仅回复原 chat/message，不复制原文；沿既有管理员 mentions 和原审核按钮。ATTEMPTED/UNKNOWN 不保证管理员实际收到：本补丁没有新增管理员扫描、补发入口或第二套状态系统，只有实际收到通知时可使用原按钮裁决；未知结果保留原 case 的30日 TTL，不能自动 CLEAN，也不宣称所有待审核均可见或已解决。首次失败与 case 写入之间同样不承诺跨服务严格一次。

caller 输入只接收现有规范产生的真 int；case 的 boto3 回读允许有限、精确整数 Decimal。统一校验正数，拒 bool、小数、非有限值及字符串；普通目标必须等于原 user，guest 目标不得等于 guest bot。callback 的无目标拒绝须发生在 selected_action 写入和任何 Telegram 处罚前，加入实际 moto 回读到 callback 的验证。

新通知还须显式传 `require_confirmation=True`（默认 False 保持旧调用），客户端仅在 `ok is True`、`result` 为 dict 且 `message_id` 为真正整数正数时返回确认；确认与 retries 是两个独立 keyword。矛盾或畸形成功响应按 ATTEMPTED/UNKNOWN，不能标 SENT 或自动重发。

## 验证与停止条件

- 先计划独审，再主代理实现；正确性、维护独立 POST。用真实 HTTP MockTransport + processor/router + stateful repository 验证：primary/recovery 413、非 413 反例、精确错误类型、不可泄露 canary、重投/lease/写失败/发送 UNKNOWN、身份变化、guest caller 三类、CLEAN 不提升、合法管理员后续动作与跨群拒绝。
- 目标测试及完整现行测试，不运行冻结的历史在线 collector 或模型评估；离线接缝使用合成数据，禁止真实 provider/AWS/Telegram 网络。
- 源码 PR/CI 与运行发布分开记。运行发布前另有限执行合同和工具 PRE，首次新真实 API/配置原文先登记独立七日期限；实际五函数 ZIP/层/配置、ARM 和稳定窗口主独证据完成后才称已部署。旧 S snapshot 不重建；不能用本次本地测试代替线上 413 再现。
- 若需新增模型许可、修改预算或无法保证无 caller 不会处罚 bot，停止该扩展并保留事实，不猜限制、不自动换模型、不清 UNKNOWN。
- 今天 Oct20、明天 Oct21 和其余原清理责任保持独立，未到期不 apply；发布/删除/UI 串行。

## 交付记录

初次独审发现 413 识别顺序和 guest 处罚对象披露缺口，原源码/失败回执保全，已窄修。83项定向测试通过；修正本机回环测试隔离设置后2519项完整回归通过（随后仅补四语言永久封禁提示及对应断言，再跑定向和CI）。CI/运行包/线上效果仍待实际回执。本契约归 Z13，相关告警事实归 Z17；20 工单状态不凭准备自动关闭。后续同步计划、证据、manifest、GitHub 工单及原自动任务，冻结历史不改写。

参考：[Groq 错误码](https://console.groq.com/docs/errors)、[Groq 组织限额说明](https://console.groq.com/docs/rate-limits)。
