# 计费事件终止顺序修复

当前为本地代码与独立复核完成，CI和运行发布待实际回执。核心owner仍为 `_cost_reports.parse_reports`，未更换费用写入者、预算阈值、价格、时间窗、扫描预留或每轮至多两个12小时块的限制。

已有查询返回1512条计费元数据，378次完整调用中有两次FINAL时间戳分别比REPORT晚19/7毫秒。旧解析器在REPORT时立即结算，错误拒绝了这两条完整链。原23:08故障确切分支与时间戳换序原因仍UNKNOWN；不据此推断整Bot掉线或额度耗尽。

只接受原START→CostStart→FINAL→REPORT及同一group/stream/RID的START→CostStart→REPORT→FINAL两种完整序列。等待FINAL期间跨新START或更换身份（含同RID重试），以及缺失/重复和schema/complete不符仍拒绝。完整结束后的同RID重试仍分别计费。采用两个终止时间的较大值，保持301000毫秒及billed_ms+1000原双上限，不新增19毫秒阈值，不补造事件。

137定向测试（28新回归）、2547全测通过；独立代码和维护复核通过。真实已捕获元数据离线重放的核心dev144/prod216各与原CloudWatch调用指标一致，18个halo调用不计入；独立逐项费用聚合一致。没有新扫描、模型或Telegram动作。证据见[evidence/2026-10-20-cost-report-repair/local.safe.json](evidence/2026-10-20-cost-report-repair/local.safe.json)。

后续发布仅替换Bot/Memory共同包中的该解析器成员，其余包/层/配置与四群状态保护。实际ARM五handler、dev→prod各唯一Execute、完整主独ZIP读回和稳定检查后，等待原定时owner自行补齐，再以新的有限只读范围确认当前预算覆盖；禁止手动Invoke/run_monitor或写许可。代码、CI或部署成功不单独代表预算恢复。共享Bot结果和当前定时恢复仍待验证；媒体测试需要新实际独占窗口和有效预算。

新增诊断原文E两份原期限Oct27 01:53:25.893115UTC；F原三份及续接两份共五份同原期限Oct27 01:57:25.452039UTC。原账本不改写，续接单独账本绑定，不能延长。今天Oct20告警341期限14:32:29.705948UTC保持；其他原职责与历史UNKNOWN不变。
