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


## 当前结果与下一步

2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。

Z20的已声明源码与在线资源范围结项；Z01/Z02最终业务回归、Z12–Z16实际恢复、Z17真实费用归因仍OPEN。先做这些可独立推进的验收，不只等待空测试群。自然使用起点未建立，0/50有据和0/20未知；至少7天实际使用及逐条来源/完整答案门槛仍未达到，production_ready=false，不启用新群或prod记忆。

运行构建仍`01bdc1da2c5d995759eda0dfef99f7b427301d60`；本批是云资源收尾与文档同步，没有新Lambda部署。F5语义policy PASS、来源1176/1176、未知256/256、已知220/224；原strict FAIL、4预算缺答、UNKNOWN和全部冻结F5–F10证据保持，不复跑或算作自然样本。

副本独立跟踪：旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。

[本批实际证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)；[副本台账](RETAINED_COPIES.md)。保留6张现役表、必要业务队列/日志/恢复数据、层/assets和当前凭据；不代表账号全资源已清空。

费用线最近归档仅是9月27日CE项目标签Estimated USD1.2690103981；未标记/共享、credits/税及模型账单仍需闭合。预算账本、未知责任与实际账单分开，应用预算不是账号硬封顶。本次没有模型或支付动作。

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
- [x] Z20 #221 — FIX: 退役旧记忆代码、核验旧设置并清理无用资源

## 完成门槛

四语言合成与真实证据分开：明确自述准确率≥95%、召回≥90%、来源支持100%、未知正确表达≥95%；身份错归属、跨群/敏感泄漏、删后复活和误删为零。自然至少7天＋50有据/20未知逐条审阅；学习p95≤5分钟，丢投恢复≤10分钟，暂停/过期/未处理计入覆盖。业务、成本与副本验收分别完成后才结束整个目标。
