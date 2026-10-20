## Oct20：完整计费终止事件顺序修复已部署两环境

运行构建源 `fd53b30b2d07704f091e0a407375d254e5705819`（PR280），两环境 Bot/Memory 共同完整ZIP `c1d665ef37d19b83e9503c2361ee1bee2d312a4dc1a125f333eae016dc5703ee`。仅 `_cost_reports.py` 一个成员变化，实际每环境唯一 Execute、主独五函数与共享层完整ZIP核对及至少300秒稳定已完成（dev 559.058932秒，prod 352.852451秒）。News/Quiz/Operations/共享层原包、身份配置、规则目标/日程、18告警与CONTROL原epoch/合法revision保护保持。文档HEAD/merge不当新的运行构建，不额外部署。

同group/stream/RID的完整START/CostStart/REPORT/FINAL可在原计时界限内接受最后两事件交换，缺失、重复、跨重试/身份、complete0及超时仍拒绝。原真实worker1512事件离线重放为378完整attempt，core dev144/prod216与原指标一致，halo18不算本块。两条FINAL比REPORT晚19ms和7ms；时间戳差异原因和历史23:08确切失败分支仍UNKNOWN。137定向/2547全测、CI三job、两环境5ARM与12包内合成检查通过；不算自然/媒体或真实故障重放。

正常调度后的有限只读：主六读 OBSERVED_PENDING、独六读 OBSERVED_PENDING；独立时点AWS UNVERIFIED / UnverifiedCost，覆盖摘要 `{"rows":33,"counts":{"covered":32,"missing":6,"short":1,"wrong_inventory":0},"first_gap_epoch":1792195200,"requested_through":1792465500}`。 此为顺序读取的时点证据，非跨行事务或模型许可；原每小时/至多两未完成12小时块、完整覆盖门和五owner不改。未通过完整原预算reader前不得开始媒体/模型。未手动Invoke/run_monitor/StartQuery、写DAY/许可/退款或清UNKNOWN。

操作器本批AWS 392次，其中10写=5PutObject+3CreateChangeSet+2Execute；含上述主独12次恢复只读，运行GH40GET，发布/CI另计。0模型/UI/自然样本，正常业务调用不归操作器计数。4群仍RELEASED_OBSERVING、自然0/50有据0/20未知/起点null/production_ready=false（自然质量未验收）。新的整体Bot/Memory包使旧N/R/S/Z整包许可失效，旧S snapshot不重建；后续有限重绑独审和新的真实Telegram窗口。原prod prepare37API含3写后因两条额外QuizRule描述变化停于Execute前，旧changeset保留未执行；V2仅将两条模板Description恢复当前直接规则en-dash，原ZIP不变，新changeset仅两Code更新，新增2写。模板问号/直接规则en-dash差异原因UNKNOWN；原失败/工具草稿/harness记录保留，不宣称首次无问题。

[运行证据](evidence/2026-10-20-cost-report-repair/release.safe.json)、[独立证据](evidence/2026-10-20-cost-report-repair/release-independent.safe.json)、[原有限契约](COST_REPORT_ORDER_REPAIR.md)。

两次 AWS 观测水位均为 1792465708，早于本次 prod Execute 完成 1792465760.097933，不能据此判断新代码定时运行失败或已经恢复。

本地汇总首次因安全 PRE 的 ISO 时间格式被数值门禁拒绝，未生成 final、无新云操作；原工具/双 PRE/once/intent/失败共八文件保全。仅四个精确冻结 PRE 允许 ISO UTC 解析的新续接经 33 正确性/25 维护控制后唯一完成，实际完整链另独审通过；运行时间门禁不变。

## 以下为此前冻结阶段；其当前包、未发布或待核摘要仅属当时，不作重跑指令

# 计费事件终止顺序修复

当前为本地代码与独立复核完成，CI和运行发布待实际回执。核心owner仍为 `_cost_reports.parse_reports`，未更换费用写入者、预算阈值、价格、时间窗、扫描预留或每轮至多两个12小时块的限制。

已有查询返回1512条计费元数据，378次完整调用中有两次FINAL时间戳分别比REPORT晚19/7毫秒。旧解析器在REPORT时立即结算，错误拒绝了这两条完整链。原23:08故障确切分支与时间戳换序原因仍UNKNOWN；不据此推断整Bot掉线或额度耗尽。

只接受原START→CostStart→FINAL→REPORT及同一group/stream/RID的START→CostStart→REPORT→FINAL两种完整序列。等待FINAL期间跨新START或更换身份（含同RID重试），以及缺失/重复和schema/complete不符仍拒绝。完整结束后的同RID重试仍分别计费。采用两个终止时间的较大值，保持301000毫秒及billed_ms+1000原双上限，不新增19毫秒阈值，不补造事件。

137定向测试（28新回归）、2547全测通过；独立代码和维护复核通过。真实已捕获元数据离线重放的核心dev144/prod216各与原CloudWatch调用指标一致，18个halo调用不计入；独立逐项费用聚合一致。没有新扫描、模型或Telegram动作。证据见[evidence/2026-10-20-cost-report-repair/local.safe.json](evidence/2026-10-20-cost-report-repair/local.safe.json)。

后续发布仅替换Bot/Memory共同包中的该解析器成员，其余包/层/配置与四群状态保护。实际ARM五handler、dev→prod各唯一Execute、完整主独ZIP读回和稳定检查后，等待原定时owner自行补齐，再以新的有限只读范围确认当前预算覆盖；禁止手动Invoke/run_monitor或写许可。代码、CI或部署成功不单独代表预算恢复。共享Bot结果和当前定时恢复仍待验证；媒体测试需要新实际独占窗口和有效预算。

新增诊断原文E两份原期限Oct27 01:53:25.893115UTC；F原三份及续接两份共五份同原期限Oct27 01:57:25.452039UTC。原账本不改写，续接单独账本绑定，不能延长。今天Oct20告警341期限14:32:29.705948UTC保持；其他原职责与历史UNKNOWN不变。
