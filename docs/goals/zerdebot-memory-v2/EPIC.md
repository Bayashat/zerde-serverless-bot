> 2026-09-28六空资源收尾：[实际删除与独审证据](evidence/2026-09-28-orphan-retirement/final.safe.json)；[本批执行契约](ORPHAN_RETIREMENT_EXECUTION.md)。原S4已结束，不重跑；本批没有运行包/配置发布。

<!-- zerde-memory-v2:EPIC -->
# ZerdeBot Memory V2 与可靠性整治

目标：可靠、可维护的群机器人；个人记忆只来自本人在本群的明确自述，回答有来源，可查看/更正/遗忘。自动社交与抽奖永久退役。Python/Lambda/SQS/DynamoDB保留，V2独立表和唯一事实writer，不重写整个仓库。

2026-09-26用户新增顺序：**启用新功能、新群或生产记忆前清除旧残留；删除前给精确准备删/保留清单；每次有实质进展及时同步计划和工单。** 现有dev测试群保持原控制/epoch，不把本次同步当成新启用。

- [完整计划](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/PLAN.md)
- [当前收尾契约](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/FINISH_EXECUTION.md)
- [删除前清单](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/RETIREMENT_INVENTORY.md)
- [任务看板](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/TASKS.md)
- [下一会话入口](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/HANDOFF.md)
- [证据](https://github.com/Bayashat/zerde-serverless-bot/blob/main/docs/goals/zerdebot-memory-v2/EVIDENCE.md)

## 当前完成与未完成

- PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。
- 2026-09-28另批两条旧updates队列及四个孤儿日志组已实际删除，六对象不存在和保留七表/十函数保护投影已独立核验；前置失败及窄修复证据保留。原7候选只剩zerde-prod-bot-stats，另有2个旧SSM参数尚待核实。冻结旧表12行与现役精确键对照中，3/4条历史统计已被现役累计覆盖，另1条统计无对应行；8条旧投票没有迁入/过期证据，不能恢复到现役。后续先保护有效统计、明确旧会话退役语义及备份恢复，再另列删除范围；R2/Z20仍OPEN，不启用新功能、新群或prod记忆。
- F5模型与F6/F7/F8/F10受控验收的冻结证据不重跑；自然使用起点仍未建立，0/50有据、0/20未知，production_ready=false。现有dev原控制/epoch保持，prod没有新增CONTROL。
- F5真实模型合成测量语义policy PASS，来源1176/1176、未知256/256、已知完整220/224；原strict FAIL、4预算缺答及UNKNOWN保留。F6/F7/F8/F10受控原生Telegram功能证据不计自然样本。
- Z03/Z04按限定scope和GitHub实际关闭记录结项；Z01/Z20/Z10及Epic仍OPEN。Z12–Z16业务恢复、Z17真实账单归因没有因资源退役完成。
- Z10原PITR复查仍为2026-10-17 16:20:38 UTC；本次删表新增SYSTEM副本已读到的实际服务到期字段为2026-11-01 11:46:02 UTC。这是复查/服务到期信息，不是已物理抹盘证明；日志/DLQ/其他副本职责继续，已移除本地密文/key不重建。

- R2/Z20新增精确私有AttributeValue临时证据副本于2026-10-04 10:35 UTC到期，本批提前完成则提前清理；它不是灾备，也不重建已到期的旧记忆归档。原10月17日PITR复查与本次11月1日SYSTEM副本服务到期分别保留；本次仅登记副本责任；自动任务由根代理按最终入口另行同步。
- 2026-09-27 10:53 UTC的CE标签归属快照，UTC区间[2026-09-01,2026-09-28)（含当前日不完整用量），UnblendedCost为dev USD0.4216791725、prod USD0.8473312256，合计USD1.2690103981，Estimated。未标Project的Usage USD25.9433726729和Tax USD4.86不分配给Zerde；不是实付、模型账单或完整Free Tier核算，不与Memory预算估算/UNKNOWN预留相加，Z17仍OPEN。 [只读补充证据](evidence/2026-09-27-retirement/followup-readonly.safe.json)。

## 工作顺序

R1同步 → R2源码和本批栈内资源已完成，继续旧stats有效语义与2个旧SSM消费者核验；R3业务及实际费用验收可独立推进；R4自然使用和推广受清理与产品门槛控制。Z20前置停写/保护证据已满足，不等原Z01/Z03 issue关闭。每次交付分别记录代码、合并、部署读回、合成、真实、删除与副本证据。

保留6张现役stats/quiz/V2表、业务队列、预算UNKNOWN和恢复数据；禁止purge混合队列。prod Retain脱管不等于物理删除。未知消费者先核实，不能为清理误删。失败仅回无长期记忆显式问答。

当前应用月目标USD70模型＋USD30新增AWS预留，沿原真实账本；不是AWS账号硬封顶或实付。Project/Environment标签ACTIVE不代表账单归因已完成；账号、项目、模型供应商费用、credits/税分别说明。

## 工单

- [ ] Z01 #158 — FIX: 停用自动互动并隔离旧记忆路径
- [ ] Z02 #159 — FIX: 日志脱敏和 Telegram 内容最小化
- [x] Z03 #160 — FIX: 旧记忆删除与业务数据边界
- [x] Z04 #161 — FIX: 统一部署配置和可复现打包
- [ ] Z05 #162 — FEATURE: Memory V2 身份、事实和控制契约
- [ ] Z06 #163 — FEATURE: 可靠消息摄取与后台恢复
- [ ] Z07 #164 — FEATURE: 明确自述抽取与个人和群档案
- [ ] Z08 #165 — FEATURE: 有来源的记忆问答与预算控制
- [ ] Z09 #166 — FEATURE: 更正、遗忘、退出与来源编辑闭环
- [ ] Z10 #167 — FIX: 旧记忆清零工具和切换演练
- [ ] Z11 #168 — FEATURE: 多语言评估、单群试运行与推广
- [ ] Z12 #169 — FIX: 验证码状态竞争与失败恢复
- [ ] Z13 #170 — FIX: 反垃圾执行结果和重试语义
- [ ] Z14 #171 — FIX: Voteban 会话身份和逻辑过期
- [ ] Z15 #172 — FIX: 新闻抓取时限与分群交付恢复
- [ ] Z16 #173 — FIX: Quiz 发布、计分与答案恢复
- [ ] Z17 #174 — FEATURE: 成本归因、dev 按需运行与有效告警
- [x] Z18 #175 — CHORE: 旧 AWS 资源清理清单与执行手册
- [x] Z19 #178 — CHORE: 移除实验性抽奖功能
- [ ] Z20 #221 — FIX: 退役旧记忆代码、核验旧设置并清理无用资源

## 完成门槛

四语言合成与真实证据分开，明确自述准确率≥95%、召回≥90%、来源支持100%、未知正确表达≥95%；身份错归属/跨群/敏感泄露/删后复活/误删为零。自然使用至少7天＋50有据和20未知逐条核对；学习p95≤5分钟、丢投恢复≤10分钟，暂停/过期缺口计入覆盖。副本义务保持原期限，PITR 2026-10-17 16:20:38UTC复查。

2026-09-26字段核验补充：旧prod的3条SETTINGS只有旧memory/agent开关与更新时间，没有style_profile；dev0行，无现役setter。故不为死开关建新settings存储；纯normalizer和V2临时媒体保留。删除前重新验证完整键/字段/类型/整行hash，有新增或变化即停并保护有效语义。这是9月26日历史核验：随后两轮fresh门禁通过并随本批旧表退役；详见FINISH_EXECUTION及新资源证据。

费用线已有9月26日CE标签归属快照：dev约$0.40、prod约$0.82，合计约$1.22（本月预估、非完整实付）；未标记/共享及税/credit/模型账单仍待归因。Z04的依赖修复及本轮五函数/配置scope已验收结项；费用归因仍是Z17未完工作，本次不是新功能启用。


下一步：2026-09-28另批两条旧updates队列及四个孤儿日志组已实际删除，六对象不存在和保留七表/十函数保护投影已独立核验；前置失败及窄修复证据保留。原7候选只剩zerde-prod-bot-stats，另有2个旧SSM参数尚待核实。冻结旧表12行与现役精确键对照中，3/4条历史统计已被现役累计覆盖，另1条统计无对应行；8条旧投票没有迁入/过期证据，不能恢复到现役。后续先保护有效统计、明确旧会话退役语义及备份恢复，再另列删除范围；R2/Z20仍OPEN，不启用新功能、新群或prod记忆。 [历史7候选只读摘要](evidence/2026-09-27-retirement/earlier-resource-candidates.safe.json)。本轮实际证据：[本轮实际资源退役证据](evidence/2026-09-27-retirement/resource-release.safe.json)。

## 本轮S4实际结果

PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。

本次预算仅在2026-09-27 11:54:48 UTC由原owner只读得到PASS_POINT_IN_TIME_NOT_A_PERMIT；不预留、不改账务、不释放UNKNOWN，也不授权后续调用或代表完整实付。

Z10原PITR复查仍为2026-10-17 16:20:38 UTC；本次删表新增SYSTEM副本已读到的实际服务到期字段为2026-11-01 11:46:02 UTC。这是复查/服务到期信息，不是已物理抹盘证明；日志/DLQ/其他副本职责继续，已移除本地密文/key不重建。
