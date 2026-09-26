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

- PR220已合并/两环境实际部署读回通过，源码72673/main54ce。2407测试/CI是代码证据，不能代替产品验收。
- F5真实模型合成测量语义policy PASS，来源1176/1176、未知256/256、已知完整220/224；原strict FAIL、4预算缺答、UNKNOWN保留。F6/F7/F8/F10原生Telegram受控功能验收完成。
- F9自然使用尚未建立起点，50有据/20未知样本仍0；production_ready=false，不承诺空等日历天数完成。prod未开学习。
- 旧在线30794行/8259向量已清零，本地3份加密归档和key已移除；3 SETTINGS保留。旧运行代码/2张bot-memory表/向量专属资源仍待Z20移除。
- Z18原清单/手册、Z19抽奖功能退役按限定范围结项；实际资源删除Z20、PITR/其他副本Z10继续，不能称物理副本全无。
- Z12–Z16业务真实恢复验收、Z17实际项目费用归因仍待完成，不依赖自然群聊天。

## 工作顺序

R1同步 → R2旧代码解耦/3 SETTINGS迁移/配置部署/资源精确删除；R3业务及实际费用验收可独立推进；R4自然使用和推广受清理与产品门槛控制。Z20前置停写/保护证据已满足，不等原Z01/Z03 issue关闭。每次交付分别记录代码、合并、部署读回、合成、真实、删除与副本证据。

保留6张现役stats/quiz/V2表、业务队列、预算UNKNOWN和恢复数据；禁止purge混合队列。prod Retain脱管不等于物理删除。未知消费者先核实，不能为清理误删。失败仅回无长期记忆显式问答。

当前应用月目标USD70模型＋USD30新增AWS预留，沿原真实账本；不是AWS账号硬封顶或实付。Project/Environment标签ACTIVE不代表账单归因已完成；账号、项目、模型供应商费用、credits/税分别说明。

## 工单

- [ ] Z01 #158 — FIX: 停用自动互动并隔离旧记忆路径
- [ ] Z02 #159 — FIX: 日志脱敏和 Telegram 内容最小化
- [ ] Z03 #160 — FIX: 旧记忆删除与业务数据边界
- [ ] Z04 #161 — FIX: 统一部署配置和可复现打包
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
- [ ] Z20 #221 — FIX: 退役旧记忆代码、迁移群设置并清理无用资源

## 完成门槛

四语言合成与真实证据分开，明确自述准确率≥95%、召回≥90%、来源支持100%、未知正确表达≥95%；身份错归属/跨群/敏感泄露/删后复活/误删为零。自然使用至少7天＋50有据和20未知逐条核对；学习p95≤5分钟、丢投恢复≤10分钟，暂停/过期缺口计入覆盖。副本义务保持原期限，PITR 2026-10-17 16:20:38UTC复查。
