> 2026-09-28六空资源收尾：[实际删除与独审证据](evidence/2026-09-28-orphan-retirement/final.safe.json)；[本批执行契约](ORPHAN_RETIREMENT_EXECUTION.md)。原S4已结束，不重跑；本批没有运行包/配置发布。

# 任务看板（2026-09-27 S4同步）

[总工单 #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)仍OPEN；逐项状态唯一来源：[task_manifest.json](task_manifest.json)。[收尾契约](FINISH_EXECUTION.md)保留R1–R4四条工作线。

PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。 [本轮实际资源退役证据](evidence/2026-09-27-retirement/resource-release.safe.json)。

2026-09-28另批两条旧updates队列及四个孤儿日志组已实际删除，六对象不存在和保留七表/十函数保护投影已独立核验；前置失败及窄修复证据保留。原7候选只剩zerde-prod-bot-stats，另有2个旧SSM参数尚待核实。冻结旧表12行与现役精确键对照中，3/4条历史统计已被现役累计覆盖，另1条统计无对应行；8条旧投票没有迁入/过期证据，不能恢复到现役。后续先保护有效统计、明确旧会话退役语义及备份恢复，再另列删除范围；R2/Z20仍OPEN，不启用新功能、新群或prod记忆。 [历史7候选只读摘要](evidence/2026-09-27-retirement/earlier-resource-candidates.safe.json)。

F5模型与F6/F7/F8/F10受控验收的冻结证据不重跑；自然使用起点仍未建立，0/50有据、0/20未知，production_ready=false。现有dev原控制/epoch保持，prod没有新增CONTROL。

| ID / 工单 | 当前状态与已完成 | 尚待完成 |
|---|---|---|
| Z01 [#158](https://github.com/Bayashat/zerde-serverless-bot/issues/158) | 旧知识与自动社交算法已从两环境实际包移除；PR226专属资源与旧配置已退役，混合主队列旧schema拒绝协议保留。 | 显式问答、自动输出为零与迟到旧任务拒绝的最终业务回归仍需逐项证据；不为验收手动Invoke。 |
| Z02 [#159](https://github.com/Bayashat/zerde-serverless-bot/issues/159) | 脱敏与内容最小化已实现并部署。 | 逐条关联日志/异常/未授权群验收证据，不以总测试数结项。 |
| Z03 [#160](https://github.com/Bayashat/zerde-serverless-bot/issues/160)（已结项：限定范围） | 原30794行/8259向量在线清零已验证；停读前及删表前精确SETTINGS门禁通过，本批两旧表及28项专属资源已不存在，六张现役表/控制保护独审通过。 | 本工单限定删除/业务边界范围已验收；历史及新SYSTEM副本责任留Z10，剩余旧stats及2个旧SSM留Z20，不宣称所有副本抹除。 |
| Z04 [#161](https://github.com/Bayashat/zerde-serverless-bot/issues/161)（已结项：限定范围） | PR223依赖修复、PR224源码退役及PR226配置资源退役已部署；两环境五函数实际包/锁定依赖/层/完整配置、预算清单及保护项主检和独审通过。 | 本工单限定部署配置/打包范围已验收；业务真实恢复、费用归因和自然质量仍由各原工单负责。 |
| Z05 [#162](https://github.com/Bayashat/zerde-serverless-bot/issues/162) | V2身份、事实、控制与唯一writer已运行并通过合成验证。 | 按原契约核对证据并收口；Z11自然使用与prod启用未完成。 |
| Z06 [#163](https://github.com/Bayashat/zerde-serverless-bot/issues/163) | 事务摄取、后台恢复已部署并有真实Telegram合成完成证据。 | 覆盖/暂停/过期分母及学习/恢复延迟分布；单次耗时不是p95。 |
| Z07 [#164](https://github.com/Bayashat/zerde-serverless-bot/issues/164) | F5真实模型合成测量语义policy PASS，原strict FAIL和4缺答保留。 | 自然使用事实正确性/来源和语言切片，未知时不编造。 |
| Z08 [#165](https://github.com/Bayashat/zerde-serverless-bot/issues/165) | 来源支持1176/1176；原生Telegram来源点击可回源。 | 自然回答质量、费用归因与预算恢复完整周期；#134关联本工单，尚不代替整体结项。 |
| Z09 [#166](https://github.com/Bayashat/zerde-serverless-bot/issues/166) | F6/F7/F8/F10及PR220完成权限拒绝、本人更正、source-forget闭环。 | 自然覆盖及各原验收项逐条收口；旧两个PENDING不回填。 |
| Z10 [#167](https://github.com/Bayashat/zerde-serverless-bot/issues/167) | 30794行/8259向量在线清零、本地3归档/key移除和本批两旧表/向量资源不存在均有实际证据；未重建旧归档。 | Z10原PITR复查仍为2026-10-17 16:20:38 UTC；本次删表新增SYSTEM副本已读到的实际服务到期字段为2026-11-01 11:46:02 UTC。这是复查/服务到期信息，不是已物理抹盘证明；日志/DLQ/其他副本职责继续，已移除本地密文/key不重建。 |
| Z11 [#168](https://github.com/Bayashat/zerde-serverless-bot/issues/168) | F5模型及F6/F7/F8/F10原生Telegram合成功能验收完成。 | 真实使用起点未建立、0/50有据和0/20未知；至少7天；新启用先过Z20清理闸门。 |
| Z12 [#169](https://github.com/Bayashat/zerde-serverless-bot/issues/169) | 验证码竞争/状态恢复实现已部署。 | 测试身份真实正确解限、旧超时/重入群竞争和异常恢复。 |
| Z13 [#170](https://github.com/Bayashat/zerde-serverless-bot/issues/170) | 反垃圾执行结果/重试及CLEAN恢复实现已部署。 | 真实删除/权限失败/计数恢复、CLEAN摄取和guest归属。 |
| Z14 [#171](https://github.com/Bayashat/zerde-serverless-bot/issues/171) | 投票会话版本和逻辑过期实现已部署。 | 真实旧按钮/新会话、并发终结及临时封禁恢复计数。 |
| Z15 [#172](https://github.com/Bayashat/zerde-serverless-bot/issues/172) | 新闻总时限和分群交付恢复实现已部署。 | 成功群不重复、失败群恢复、结果不明处理的实际证据。 |
| Z16 [#173](https://github.com/Bayashat/zerde-serverless-bot/issues/173) | Quiz发布/计分/答案恢复实现已部署。 | 真实poll、答案先于持久可见、重投只计一次和reconcile闭环。 |
| Z17 [#174](https://github.com/Bayashat/zerde-serverless-bot/issues/174) | 成本/通知修复已部署；Project/Environment标签ACTIVE；9月27日10:53 UTC的CE可归属dev USD0.4216791725/prod USD0.8473312256，合计USD1.2690103981（Estimated）。 | 闭合账期项目归因、未标记/共享费用、credits/税及模型账单；USD1.2690103981非实付或完整Free Tier结论，业务恢复证据仍待收口。 |
| Z18 [#175](https://github.com/Bayashat/zerde-serverless-bot/issues/175)（已结项：限定范围） | 原清单与执行手册已由#184/#204交付，限定文档范围已结项；本批S4资源退役另有实际证据。 | 剩余旧stats及2个旧SSM仍由Z20继续；本工单关闭不代表账号全资源或所有副本已清空。 |
| Z19 [#178](https://github.com/Bayashat/zerde-serverless-bot/issues/178)（已结项：限定范围） | 抽奖命令/实现/定时恢复已退役，在线残留清除和旧任务重放已验证。 | 功能范围可结项；历史副本义务明确留在Z10，不宣称物理抹除。 |
| Z20 [#221](https://github.com/Bayashat/zerde-serverless-bot/issues/221) | PR224的13旧算法模块及PR226专用入口/env/IAM/14项每环境资源已部署退役；两环境共28项物理不存在和五函数/保护项已独审。 A/B/C已完成有限只读分类/引用/副本元数据核验：12行=4审核统计+8投票状态，Scheduler/Pipes及所查副本元数据未发现匹配项。 9月28日另批2旧updates队列/4孤儿日志已实际删除并独立读回；本批六对象不存在、七保留表/十函数保护投影相同，无新运行发布。 | 2026-09-28另批两条旧updates队列及四个孤儿日志组已实际删除，六对象不存在和保留七表/十函数保护投影已独立核验；前置失败及窄修复证据保留。原7候选只剩zerde-prod-bot-stats，另有2个旧SSM参数尚待核实。冻结旧表12行与现役精确键对照中，3/4条历史统计已被现役累计覆盖，另1条统计无对应行；8条旧投票没有迁入/过期证据，不能恢复到现役。后续先保护有效统计、明确旧会话退役语义及备份恢复，再另列删除范围；R2/Z20仍OPEN，不启用新功能、新群或prod记忆。 临时AV到期责任仍归旧stats批次，不因六空资源完成而取消。 |

Z03/Z04仅按已验收scope及GitHub实际关闭读回标结项；Z01/Z20/Z10、业务/费用和Epic继续OPEN。Z18/Z19仍是原限定范围结项，不按测试数批量关闭。

R2下一步据A/B/C既有分类继续处理旧stats有效语义、2个旧SSM消费者与恢复边界，R3验证码/反垃圾/投票/News/Quiz及真实费用可独立推进；禁止为验收手动Lambda Invoke。没有单群公开入口的业务由原调度或另立公开入口计划覆盖，不宣称已测。R4不以空群日历天数凑自然验收。

本次预算仅在2026-09-27 11:54:48 UTC由原owner只读得到PASS_POINT_IN_TIME_NOT_A_PERMIT；不预留、不改账务、不释放UNKNOWN，也不授权后续调用或代表完整实付。

旧状态字段与旧evidence保持历史，不是重跑指令；代码、部署、质量、在线清零、资源不存在和副本消退分别验收。

最新A/B/C及CE时点见[只读补充证据](evidence/2026-09-27-retirement/followup-readonly.safe.json)。R2/Z20新增精确私有AttributeValue临时证据副本于2026-10-04 10:35 UTC到期，本批提前完成则提前清理；它不是灾备，也不重建已到期的旧记忆归档。原10月17日PITR复查与本次11月1日SYSTEM副本服务到期分别保留；本次仅登记副本责任；自动任务由根代理按最终入口另行同步。
