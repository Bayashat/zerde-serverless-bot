<!-- zerde-memory-v2:EPIC -->
# ZerdeBot Memory V2 与可靠性整治

本 Epic 执行 2026-09-10 用户批准的完整方案。目标是明确自述、证据事实、跨群隔离、可更正和遗忘的群机器人记忆，关闭所有自动社交参与，同时修复审阅发现的可靠性问题。

- [完整实施契约](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/PLAN.md)
- [审阅与 AWS 账单快照](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/AUDIT.md)
- [下一会话执行入口](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/GOAL.md)
- [证据记录](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/EVIDENCE.md)
- [最终代码集成 PR #204](https://github.com/Bayashat/zerde-serverless-bot/pull/204)
- [代码交付后继续执行](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/HANDOFF.md)

当前 Z01–Z19 均已有独立代码/工具/手册 PR，详见[任务看板](https://github.com/Bayashat/zerde-serverless-bot/blob/feat/zerde-complete-integration/docs/goals/zerdebot-memory-v2/TASKS.md)。**PR_OPEN / IMPLEMENTED_UNPROVEN**：尚未合并、部署、清零、运行真实模型或七天试运行，不勾选产品完成。

2026-09-11用户修订：直接在#204移除实验性抽奖，待用户审阅批准合并；此次没有部署或删除线上数据。

## 不可漂移的边界

保留 Python/Lambda/SQS/DynamoDB；独立 V2 表、唯一 fact writer；profile 只读当前有效事实。各群隔离，只本人明确自述；原文30天，长期最小证据随事实维护；全部自动插话/reaction/频道评论关闭，显式问答独立可用。旧 reader/writer/task/import/backfill 先停，再按精确清单清零，保留settings、统计、验证码和其他业务数据；用户已取消抽奖，其残留仅通过显式退役root清单清理。不能整表删除或 purge 混用业务队列。V1 无向量检索，失败只能回无长期记忆问答。

新增记忆目标$10/月（$7模型预留计数+$3AWS用量预留），不是AWS账号硬止付。费用必须区分账号与项目，历史credits抵扣不是FreeTier全免。Z18仅清理清单/手册，不授权删除旧云资源。

## 完成门槛

至少200多轮场景、300标注事实、100无依据问题，kk/ru/en/混语分切片；precision>=95%、recall>=90%、个人断言来源支持100%、未知正确表达>=95%；错误身份/跨群/敏感泄露/删除复活/业务误删均0。dev验证后单群至少7天并取得50事实问答及20未知问答；样本不足不算真实验收。普通学习p95<=5min，投递恢复<=10min单列。

每任务独立PR，代码、合并、部署读回、合成与真实证据分开记录；不能因为测试通过就关闭产品验收。先Z01-Z04，之后Z05-Z11按依赖推进；独立业务Z12-Z16可并行，共享入口及infra统一集成。

## 子工单

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
- [ ] Z18 #175 — CHORE: 旧 AWS 资源清理清单与执行手册

## 旧工单

#135 被清零后重新学习方案取代；#133 延期；#134 来源链接纳入Z08，实际链接验收完成后再关闭。

## 执行中新发现的必要修复

- [ ] [Z19 移除实验性抽奖](https://github.com/Bayashat/zerde-serverless-bot/issues/178)：用户取消该实验；命令、观察、存储和定时恢复从#204移除，旧任务无副作用消费，残留数据可按精确scope清理。取代原#181事务修复。
