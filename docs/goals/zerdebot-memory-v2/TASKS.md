# 任务看板（2026-09-30反馈修复发布）

[逐项状态唯一来源](task_manifest.json)；[本轮发布证据](evidence/2026-09-30-quiz-feedback/release.safe.json)。代码、上线、真实业务、自然质量与副本消退分别验收。

| 工单 | 已完成 | 仍待完成 |
|---|---|---|
| Z01 [#158](https://github.com/Bayashat/zerde-serverless-bot/issues/158) | 旧知识与自动社交算法已从两环境实际包移除；PR226专属资源与旧配置已退役，混合主队列旧schema拒绝协议保留。 | 显式问答、自动输出为零与迟到旧任务拒绝的最终业务回归仍需逐项证据；不为验收手动Invoke。 |
| Z02 [#159](https://github.com/Bayashat/zerde-serverless-bot/issues/159) | 脱敏与内容最小化已实现并部署。 PR232限定Quiz调用链移除内容/异常正文日志并交付安全attempt/usage观察；全仓逐项日志验收仍待。 PR235收紧实际Quiz反馈发送器的异常日志，只记录错误类型；全仓逐项日志证据仍待。 | 逐条关联日志/异常/未授权群验收证据，不以总测试数结项。 |
| Z03 [#160](https://github.com/Bayashat/zerde-serverless-bot/issues/160)（限定范围已结项） | 原30794行/8259向量在线清零已验证；停读前及删表前精确SETTINGS门禁通过，本批两旧表及28项专属资源已不存在，六张现役表/控制保护独审通过。 | 本工单原限定范围已验收；Z20已完成声明的在线退役，Z10继续副本责任，不宣称账号全资源或全部副本已清空。 |
| Z04 [#161](https://github.com/Bayashat/zerde-serverless-bot/issues/161)（限定范围已结项） | PR223依赖修复、PR224源码退役及PR226配置资源退役已部署；两环境五函数实际包/锁定依赖/层/完整配置、预算清单及保护项主检和独审通过。 | 本工单限定部署配置/打包范围已验收；业务真实恢复、费用归因和自然质量仍由各原工单负责。 |
| Z05 [#162](https://github.com/Bayashat/zerde-serverless-bot/issues/162) | V2身份、事实、控制与唯一writer已运行并通过合成验证。 | 按原契约核对证据并收口；Z11自然使用与prod启用未完成。 |
| Z06 [#163](https://github.com/Bayashat/zerde-serverless-bot/issues/163) | 事务摄取、后台恢复已部署并有真实Telegram合成完成证据。 | 覆盖/暂停/过期分母及学习/恢复延迟分布；单次耗时不是p95。 |
| Z07 [#164](https://github.com/Bayashat/zerde-serverless-bot/issues/164) | F5真实模型合成测量语义policy PASS，原strict FAIL和4缺答保留。 | 自然使用事实正确性/来源和语言切片，未知时不编造。 |
| Z08 [#165](https://github.com/Bayashat/zerde-serverless-bot/issues/165) | 来源支持1176/1176；原生Telegram来源点击可回源。 | 自然回答质量、费用归因与预算恢复完整周期；#134关联本工单，尚不代替整体结项。 |
| Z09 [#166](https://github.com/Bayashat/zerde-serverless-bot/issues/166) | F6/F7/F8/F10及PR220完成权限拒绝、本人更正、source-forget闭环。 | 自然覆盖及各原验收项逐条收口；旧两个PENDING不回填。 |
| Z10 [#167](https://github.com/Bayashat/zerde-serverless-bot/issues/167) | 30794行/8259向量在线清零、本地3归档/key移除和本批两旧表/向量资源不存在均有实际证据；未重建旧归档。 最后旧stats在线退役及精确临时AV移除已独审；新USER/SYSTEM副本已登记。 | 副本独立跟踪：旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。 日志/DLQ/其他副本仍按原台账逐项收口，用户Telegram导出不删。 |
| Z11 [#168](https://github.com/Bayashat/zerde-serverless-bot/issues/168) | F5模型及F6/F7/F8/F10原生Telegram合成功能验收完成。 | Z20声明的旧残留清理前置已满足；真实使用起点未建立，0/50有据和0/20未知，至少7天及其他产品门槛仍未满足；本次不启用新群或prod记忆。 |
| Z12 [#169](https://github.com/Bayashat/zerde-serverless-bot/issues/169) | 验证码竞争/状态恢复实现已部署。 | 测试身份真实正确解限、旧超时/重入群竞争和异常恢复。 |
| Z13 [#170](https://github.com/Bayashat/zerde-serverless-bot/issues/170) | 反垃圾执行结果/重试及CLEAN恢复实现已部署。 | 真实删除/权限失败/计数恢复、CLEAN摄取和guest归属。 |
| Z14 [#171](https://github.com/Bayashat/zerde-serverless-bot/issues/171) | 投票会话版本和逻辑过期实现已部署。 | 真实旧按钮/新会话、并发终结及临时封禁恢复计数。 |
| Z15 [#172](https://github.com/Bayashat/zerde-serverless-bot/issues/172) | 新闻总时限和分群交付恢复实现已部署。 | 成功群不重复、失败群恢复、结果不明处理的实际证据。 |
| Z16 [#173](https://github.com/Bayashat/zerde-serverless-bot/issues/173) | Quiz发布/计分/答案恢复实现已部署；9月28日dev专用群单次原生命令、真实poll与实际答题正常链路通过：发布DONE、答案SCORED，总分0→1、周分0，两条对应outbox缺席。 9月29日管理员对已DONE原题执行一次公开原生Reply对账成功；八个精确记录前后及独立强读完全相同，总分仍1，无新增poll或重复计分。 PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。 一次真实dev公开发题在受控准入失败后保留原GENERATING/outbox；撤销临时限制后，同request/generation自动成为DONE并出现一个真实poll。执行记录创建至完成289秒，后续正常恢复cursor再次推进且题目/poll不变、outbox缺席；主检与独立读回通过。原角色策略、函数配置和Memory控制保持，临时policy已提前撤销并在固定窗口结束后再次确认不存在。 PR235已合并并部署dev/prod：原请求确认保留后提示后台继续尝试且无需重发；处理中、待核对、过期和无效请求分别说明；提示发送或诊断失败不再重试整次出题。实际sendMessage异常日志仅记录类型。原publication/outbox/准入与计分所有者不变。 | 新版反馈的真实Telegram补验、daily并发、发送UNKNOWN到DONE、答案先到/GSI迟到及其他失败重投仍未覆盖；不以本地测试或发布成功关闭Z16。其余R3业务/实际费用继续，自然0/50有据、0/20未知，production_ready=false。 |
| Z17 [#174](https://github.com/Bayashat/zerde-serverless-bot/issues/174) | 成本/通知修复已部署；Project/Environment标签ACTIVE；9月27日10:53 UTC的CE可归属dev USD0.4216791725/prod USD0.8473312256，合计USD1.2690103981（Estimated）。 PR232交付Quiz应用尝试/usage未知观察及新运行包预算reader重绑；观察不是完整供应商账单。 9月30日受控Quiz恢复后原PT日计数0→1；有限窗口provider观察见新证据，不当完整账单或Memory许可。 PR235发布后104文件原费用闭包逐字保留、reader重绑时点PASS；没有新增模型测试或账单查询。 | 闭合账期项目归因、未标记/共享费用、credits/税及模型账单；USD1.2690103981非实付或完整Free Tier结论，业务恢复证据仍待收口。 |
| Z18 [#175](https://github.com/Bayashat/zerde-serverless-bot/issues/175)（限定范围已结项） | 原清单与执行手册已由#184/#204交付，限定文档范围已结项；本批S4资源退役另有实际证据。 | 本工单原限定范围已验收；Z20已完成声明的在线退役，Z10继续副本责任，不宣称账号全资源或全部副本已清空。 |
| Z19 [#178](https://github.com/Bayashat/zerde-serverless-bot/issues/178)（限定范围已结项） | 抽奖命令/实现/定时恢复已退役，在线残留清除和旧任务重放已验证。 | 功能范围可结项；历史副本义务明确留在Z10，不宣称物理抹除。 |
| Z20 [#221](https://github.com/Bayashat/zerde-serverless-bot/issues/221)（限定范围已结项） | 2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。 | 已声明源码及在线资源范围结项；备份到期责任转由Z10统一跟踪，Z01最终业务回归及R3/R4仍待完成。 |

[副本台账](RETAINED_COPIES.md)；本轮没有新增自然样本，prod记忆仍未启用。
