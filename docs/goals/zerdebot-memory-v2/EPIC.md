## 2026-09-30：真实受控准入失败已自动恢复

一次真实dev公开发题在受控准入失败后保留原GENERATING/outbox；撤销临时限制后，同request/generation自动成为DONE并出现一个真实poll。执行记录创建至完成289秒，后续正常恢复cursor再次推进且题目/poll不变、outbox缺席；主检与独立读回通过。原角色策略、函数配置和Memory控制保持，临时policy已提前撤销并在固定窗口结束后再次确认不存在。

本次仅通过一个受控准入失败恢复及有限窗口不重复，不覆盖daily并发、发送UNKNOWN、GSI迟到、其他失败重投或自然记忆质量。下一步先修正已排队请求仍提示用户重发的反馈，再继续原Z16及其他R3业务/费用验收；Z16/Z17保持OPEN，production_ready=false。

[本轮脱敏证据](evidence/2026-09-30-r3-admission-recovery/result.safe.json)。本轮没有新Lambda发布、新群/生产记忆启用或付款变更；运行构建仍为PR232的`0c6529d5c33b9afdf1229c559c83f961f04bc03f`。19项主工具及22项独立工具本地检查只验证操作器，真实结果由本轮原生操作、持久记录和独立云读回证明。

## 此前发布记录：2026-09-30 Quiz准入修订

PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。

运行构建源`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，merge`4fda918ab5e5a8f4b65e349c9d6cfb6902d40181`；两环境300秒窗口后的配置重读通过，workflow ACTIVE，新104文件预算reader时点PASS（非持续许可或账单）。[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；[下一验收契约](R3_QUIZ_ADMISSION_RECOVERY.md)。本节记录PR232发布时点；后续受控恢复结果以上方最新记录为准。

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

9月29日补充：管理员对昨日已完成的原始Quiz执行一次公开原生Reply对账，返回成功。八个精确记录前后与独立强读逐值相同，总分保持1、周分0、两个outbox缺席；UI只新增对账文字，没有新poll。仅通过DONE终态幂等边界，UNKNOWN恢复、故障重投和daily并发仍未覆盖，不增加自然样本。 见[脱敏证据](evidence/2026-09-29-r3-quiz-reconcile/result.safe.json)。

9月28日晚补充：dev专用群一次原生命令→真实poll→实际答题正常链路通过；发布DONE、答案SCORED、总分增加1、周分保持0。Z16继续OPEN，异常恢复未覆盖，非自然记忆样本。见[本轮验收](R3_QUIZ_ACCEPTANCE.md)。

2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。

Z20的已声明源码与在线资源范围结项；Z01/Z02最终业务回归、Z12–Z16实际恢复、Z17真实费用归因仍OPEN。先做这些可独立推进的验收，不只等待空测试群。自然使用起点未建立，0/50有据和0/20未知；至少7天实际使用及逐条来源/完整答案门槛仍未达到，production_ready=false，不启用新群或prod记忆。

当前运行构建源`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，PR232发布证据见上方；9月28日资源清理当时没有新Lambda部署。F5语义policy PASS、来源1176/1176、未知256/256、已知220/224；原strict FAIL、4预算缺答、UNKNOWN和全部冻结F5–F10证据保持，不复跑或算作自然样本。

副本独立跟踪：旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。

[本批实际证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)；[副本台账](RETAINED_COPIES.md)。保留6张现役表、必要业务队列/日志/恢复数据、层/assets和当前凭据；不代表账号全资源已清空。

费用线最近归档仅是9月27日CE项目标签Estimated USD1.2690103981；未标记/共享、credits/税及模型账单仍需闭合。预算账本、未知责任与实际账单分开，应用预算不是账号硬封顶。此前在线退役批次没有模型或支付动作；9月28日晚Quiz验收有真实生成请求，无充值或支付设置变更。

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
