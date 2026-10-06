## 2026-10-06晚：显式问答准入缺口本地修复，发布待验

Z01公开问答回归准备时，核对PR242发布源码与当前源码发现：原共享Gemini计数器遇DynamoDB ClientError返回`(0, True)`，显式客户端只检查布尔值，可能继续请求模型。该具体路径已本地修复：每次应用尝试要求严格正整数计数和真实bool；无效准入抛出独立异常，终止本次链路，不再尝试Gemini或切备用供应商。共享计数writer、Memory五费用owner、原账本和UNKNOWN责任不改。已经发生的先前模型尝试不由此撤销或重算。

新增18个回归，修复前15失败/3通过，修复后127定向通过；独立正确性和维护审查通过。全测首轮因执行器umask077改变测试预期目录权限而1失败/2374通过，原回执保全，随后标准umask022完整2375测试通过（1个原SDK弃用警告），全部pre-commit通过。CI、两环境实际发布、实际包验收和预算reader重新绑定尚待，不把本地修复写成已上线。Z01/Z17/Epic均保持OPEN，当前运行仍PR242，未发送新Telegram测试或调用模型，自然0/50有据、0/20未知，production_ready=false。

[本轮有限契约](EXPLICIT_QUOTA_GUARD.md)。修复完成后再继续Z01有限真实问答；既有共享writer坏存量字段的转换/补齐、完整备用供应商计费证据另留原工单，不用本修复关闭所有计费问题。七项副本/原文期限沿[原台账](RETAINED_COPIES.md)，不启用新群或prod记忆。

# 任务看板（2026-10-06：账号发票已核，供应商登录待完成）

[逐项唯一状态](task_manifest.json)；[最新费用证据](evidence/2026-10-06-provider-cost-gaps/result.safe.json)。

| 工单 | 已完成 | 仍待完成 |
|---|---|---|
| Z01 [#158](https://github.com/Bayashat/zerde-serverless-bot/issues/158) | 旧知识与自动社交算法已从两环境实际包移除；PR226专属资源与旧配置已退役，混合主队列旧schema拒绝协议保留。 | 显式问答、自动输出为零与迟到旧任务拒绝的最终业务回归仍需逐项证据；不为验收手动Invoke。 |
| Z02 [#159](https://github.com/Bayashat/zerde-serverless-bot/issues/159)（限定范围已结项） | 日志脱敏与内容最小化按原批准范围完成：原Webhook/formatter/Telegram边界及真实库重试已有证据，CloudWatch发现的topic出口经PR240修复，最后同步Lambda异常正文出口经PR242修复并部署dev/prod；两环境实际包/层/配置主独读回及17例新实包探针通过。 | 本工单原有限实现与验收范围已完成；历史CloudWatch FAIL永久保留，9份原文2026-10-08 17:13:39.091570UTC精确清理仍归副本台账与自动任务。其它业务恢复、Quiz精确UI链接、费用账单和自然使用由原工单继续，不声称全部历史日志安全。 |
| Z03 [#160](https://github.com/Bayashat/zerde-serverless-bot/issues/160)（限定范围已结项） | 原30794行/8259向量在线清零已验证；停读前及删表前精确SETTINGS门禁通过，本批两旧表及28项专属资源已不存在，六张现役表/控制保护独审通过。 | 本工单原限定范围已验收；Z20已完成声明的在线退役，Z10继续副本责任，不宣称账号全资源或全部副本已清空。 |
| Z04 [#161](https://github.com/Bayashat/zerde-serverless-bot/issues/161)（限定范围已结项） | PR223依赖修复、PR224源码退役及PR226配置资源退役已部署；两环境五函数实际包/锁定依赖/层/完整配置、预算清单及保护项主检和独审通过。 | 本工单限定部署配置/打包范围已验收；业务真实恢复、费用归因和自然质量仍由各原工单负责。 |
| Z05 [#162](https://github.com/Bayashat/zerde-serverless-bot/issues/162) | V2身份、事实、控制与唯一writer已运行并通过合成验证。 | 按原契约核对证据并收口；Z11自然使用与prod启用未完成。 |
| Z06 [#163](https://github.com/Bayashat/zerde-serverless-bot/issues/163) | 事务摄取、后台恢复已部署并有真实Telegram合成完成证据。 | 覆盖/暂停/过期分母及学习/恢复延迟分布；单次耗时不是p95。 |
| Z07 [#164](https://github.com/Bayashat/zerde-serverless-bot/issues/164) | F5真实模型合成测量语义policy PASS，原strict FAIL和4缺答保留。 | 自然使用事实正确性/来源和语言切片，未知时不编造。 |
| Z08 [#165](https://github.com/Bayashat/zerde-serverless-bot/issues/165) | 来源支持1176/1176；原生Telegram来源点击可回源。 | 自然回答质量、费用归因与预算恢复完整周期；#134关联本工单，尚不代替整体结项。 |
| Z09 [#166](https://github.com/Bayashat/zerde-serverless-bot/issues/166) | F6/F7/F8/F10及PR220完成权限拒绝、本人更正、source-forget闭环。 | 自然覆盖及各原验收项逐条收口；旧两个PENDING不回填。 |
| Z10 [#167](https://github.com/Bayashat/zerde-serverless-bot/issues/167) | 30794行/8259向量在线清零、本地3归档/key移除和本批两旧表/向量资源不存在均有实际证据；未重建旧归档。 最后旧stats在线退役及精确临时AV移除已独审；新USER/SYSTEM副本已登记。 旧stats的唯一USER恢复备份 `zerde-retirement-stats-20260928` 已删除，主检和独立查询均确认精确备份不存在。删除请求实际始于2026-10-05T08:18:54.216996Z，比原期限晚18.264秒；没有提前删除或延长期限。一次DeleteBackup获HTTP200且原身份一致，独立17次只读确认旧表仍不存在、六张现役表身份/PITR配置投影及两份SYSTEM完整元数据保持。 | Z10继续OPEN：CloudWatch九份原文于10月8日17:13:39.091570UTC、九月费用九份原文于10月11日17:01:48.147210UTC精确清理；原PITR于10月17日16:20:38UTC复查；旧memory SYSTEM于11月1日11:46:02.425UTC、旧stats SYSTEM于11月2日08:45:11.254UTC服务到期后精确只读核验。日志/DLQ及其他原台账责任保持；用户导出、现役PITR和业务恢复数据保留。 新增本轮Quiz原始证据及登记派生于2026-10-12 17:15:22.532382UTC精确人工清理并独审，不延长其它原期限。 新增3份账号发票原文于2026-10-13 08:06:04.659429UTC精确人工清理并独审；V2采用原更早期限，现共七项责任，不延长原六期限。 |
| Z11 [#168](https://github.com/Bayashat/zerde-serverless-bot/issues/168) | F5模型及F6/F7/F8/F10原生Telegram合成功能验收完成。 | Z20声明的旧残留清理前置已满足；真实使用起点未建立，0/50有据和0/20未知，至少7天及其他产品门槛仍未满足；本次不启用新群或prod记忆。 |
| Z12 [#169](https://github.com/Bayashat/zerde-serverless-bot/issues/169) | 验证码竞争/状态恢复实现已部署。 | 测试身份真实正确解限、旧超时/重入群竞争和异常恢复。 |
| Z13 [#170](https://github.com/Bayashat/zerde-serverless-bot/issues/170) | 反垃圾执行结果/重试及CLEAN恢复实现已部署。 | 真实删除/权限失败/计数恢复、CLEAN摄取和guest归属。 |
| Z14 [#171](https://github.com/Bayashat/zerde-serverless-bot/issues/171) | 投票会话版本和逻辑过期实现已部署。 | 真实旧按钮/新会话、并发终结及临时封禁恢复计数。 |
| Z15 [#172](https://github.com/Bayashat/zerde-serverless-bot/issues/172) | 新闻总时限和分群交付恢复实现已部署。 | 成功群不重复、失败群恢复、结果不明处理的实际证据。 |
| Z16 [#173](https://github.com/Bayashat/zerde-serverless-bot/issues/173) | Quiz发布/计分/答案恢复实现已部署；9月28日dev专用群单次原生命令、真实poll与实际答题正常链路通过：发布DONE、答案SCORED，总分0→1、周分0，两条对应outbox缺席。 9月29日管理员对已DONE原题执行一次公开原生Reply对账成功；八个精确记录前后及独立强读完全相同，总分仍1，无新增poll或重复计分。 PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。 一次真实dev公开发题在受控准入失败后保留原GENERATING/outbox；撤销临时限制后，同request/generation自动成为DONE并出现一个真实poll。执行记录创建至完成289秒，后续正常恢复cursor再次推进且题目/poll不变、outbox缺席；主检与独立读回通过。原角色策略、函数配置和Memory控制保持，临时policy已提前撤销并在固定窗口结束后再次确认不存在。 PR235已合并并部署dev/prod：原请求确认保留后提示后台继续尝试且无需重发；处理中、待核对、过期和无效请求分别说明；提示发送或诊断失败不再重试整次出题。实际sendMessage异常日志仅记录类型。原publication/outbox/准入与计分所有者不变。 新版真实提示已在专用dev群出现：请求已保存、后台重试、无需重发；原生Reply点击可跳回本轮命令。同请求在受控准入失败后自动恢复DONE，创建至完成176秒；两个后续观察的题目/poll不变、outbox缺席，恢复cursor继续推进。临时权限限制已提前撤销，截止时间后再核原策略恢复；独立30次只读核验确认同请求完成、原权限/配置/控制保持。 10月5日晚仅完成一条新公开Quiz发题、一次未确认提交成功的原生点击及临时权限撤销；到期后看护确认恢复。最后主读取答案缺席、分数未变，有界日志未观察到poll_answer；这些结果不证明请求未到达，也不证明重送或一次计分通过。 独立37次只读确认原权限与dev保护恢复；业务结论仍PARTIAL。 | 答案重送验收仍未完成：本轮没有确认投票提交、同update_id的失败/成功完整Lambda请求链。原9月30日反馈ID/精确Reply链接仍缺；daily并发、发送UNKNOWN、答案先到/GSI迟到及其他失败重投待证。不重跑冻结题或改变门槛。Z16保持OPEN，production_ready=false。 |
| Z17 [#174](https://github.com/Bayashat/zerde-serverless-bot/issues/174) | 九月UTC整月CE固定范围6读及独立复算完成：Zerde标签Usage USD1.4977694507（dev0.5206115692/prod0.9771578815），Estimated=false；Google九月使用日期报表CSV独立复算：dev Gemini服务小计0.605498、prod Zerde项目小计0.438845 USD，PT口径与AWS UTC分列。已有计量/通知修复及Quiz准入恢复证据保持。 10月6日AWS账号九月一张发票摘要及独立原始复算通过：税前38.65＋税6.18＝44.83 USD；并非Zerde独立费用或已付款。 | 完整产品实付仍UNKNOWN：AWS未标/共享与税/credits不能猜分，付款及九月历史Free Tier未核；CE与发票税前差0.0074992985 USD原因未知。Groq/DeepSeek官方页均需用户登录，九月消费UNKNOWN；Google非秘密运行映射/税/付款仍待。dev空轮询比较、真实故障恢复预算通知和Quiz恢复保护继续；不因查账关闭Z17。 |
| Z18 [#175](https://github.com/Bayashat/zerde-serverless-bot/issues/175)（限定范围已结项） | 原清单与执行手册已由#184/#204交付，限定文档范围已结项；本批S4资源退役另有实际证据。 | 本工单原限定范围已验收；Z20已完成声明的在线退役，Z10继续副本责任，不宣称账号全资源或全部副本已清空。 |
| Z19 [#178](https://github.com/Bayashat/zerde-serverless-bot/issues/178)（限定范围已结项） | 抽奖命令/实现/定时恢复已退役，在线残留清除和旧任务重放已验证。 | 功能范围可结项；历史副本义务明确留在Z10，不宣称物理抹除。 |
| Z20 [#221](https://github.com/Bayashat/zerde-serverless-bot/issues/221)（限定范围已结项） | 2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。 | 已声明源码及在线资源范围结项；备份到期责任转由Z10统一跟踪，Z01最终业务回归及R3/R4仍待完成。 |

[副本台账](RETAINED_COPIES.md)；未新增自然样本或prod记忆。
