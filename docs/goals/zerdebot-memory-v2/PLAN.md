## Oct20：历史费用缺块已补齐，AWS估算恢复为已核验

PR280部署后的新主独各六次只读一致：39 DAY行，38完整、0缺席、1当前块短覆盖、0错inventory；此前6个缺失历史块已补齐。AWS为`ESTIMATE_VERIFIED / OBSERVED_GROSS_ESTIMATE`、paused=false，估算5,321,387 microUSD。观察时间07:08:30UTC，覆盖至06:50:00UTC，有效至10:08:30UTC，均为当时证据，不是持续许可或实付账单。

本次严格检查请求覆盖到07:05UTC，当前块差900秒，所以两份原结果仍`OBSERVED_PENDING`。原运行AWS门允许3小时内的有效覆盖，该差距不等于历史缺块或AWS门仍失败；原结果不改写。完整五owner模型预算和当前包媒体绑定仍未核验，不能据这12读发送媒体。运行源仍PR280 `fd53b30b2d07704f091e0a407375d254e5705819`，本轮没有部署、云写、模型或Telegram操作。

实际独立原响应POST通过；12份原文统一到期 **2026-10-27 07:23:59.115275UTC**，总计十三项独立副本职责。下一优先离线完成当前包与原owner/reader/媒体工具绑定，再按新的直接人类独占窗口和完整原预算检查继续；不为移动计量水位反复六读。今日告警341与明日首发527期限保持。四群已启用、自然质量仍待发布后观察，20任务14OPEN/6CLOSED与EpicOPEN不变。[本批契约](COST_RECOVERY_FOLLOWUP.md)；[副本职责](RETAINED_COPIES.md)。

## 以下为此前冻结阶段；旧时点和当前状态仅属当时，不作重跑指令

## Oct20：完整计费终止事件顺序修复已部署两环境

运行构建源 `fd53b30b2d07704f091e0a407375d254e5705819`（PR280），两环境 Bot/Memory 共同完整ZIP `c1d665ef37d19b83e9503c2361ee1bee2d312a4dc1a125f333eae016dc5703ee`。仅 `_cost_reports.py` 一个成员变化，实际每环境唯一 Execute、主独五函数与共享层完整ZIP核对及至少300秒稳定已完成（dev 559.058932秒，prod 352.852451秒）。News/Quiz/Operations/共享层原包、身份配置、规则目标/日程、18告警与CONTROL原epoch/合法revision保护保持。文档HEAD/merge不当新的运行构建，不额外部署。

同group/stream/RID的完整START/CostStart/REPORT/FINAL可在原计时界限内接受最后两事件交换，缺失、重复、跨重试/身份、complete0及超时仍拒绝。原真实worker1512事件离线重放为378完整attempt，core dev144/prod216与原指标一致，halo18不算本块。两条FINAL比REPORT晚19ms和7ms；时间戳差异原因和历史23:08确切失败分支仍UNKNOWN。137定向/2547全测、CI三job、两环境5ARM与12包内合成检查通过；不算自然/媒体或真实故障重放。

正常调度后的有限只读：主六读 OBSERVED_PENDING、独六读 OBSERVED_PENDING；独立时点AWS UNVERIFIED / UnverifiedCost，覆盖摘要 `{"rows":33,"counts":{"covered":32,"missing":6,"short":1,"wrong_inventory":0},"first_gap_epoch":1792195200,"requested_through":1792465500}`。 此为顺序读取的时点证据，非跨行事务或模型许可；原每小时/至多两未完成12小时块、完整覆盖门和五owner不改。未通过完整原预算reader前不得开始媒体/模型。未手动Invoke/run_monitor/StartQuery、写DAY/许可/退款或清UNKNOWN。

操作器本批AWS 392次，其中10写=5PutObject+3CreateChangeSet+2Execute；含上述主独12次恢复只读，运行GH40GET，发布/CI另计。0模型/UI/自然样本，正常业务调用不归操作器计数。4群仍RELEASED_OBSERVING、自然0/50有据0/20未知/起点null/production_ready=false（自然质量未验收）。新的整体Bot/Memory包使旧N/R/S/Z整包许可失效，旧S snapshot不重建；后续有限重绑独审和新的真实Telegram窗口。原prod prepare37API含3写后因两条额外QuizRule描述变化停于Execute前，旧changeset保留未执行；V2仅将两条模板Description恢复当前直接规则en-dash，原ZIP不变，新changeset仅两Code更新，新增2写。模板问号/直接规则en-dash差异原因UNKNOWN；原失败/工具草稿/harness记录保留，不宣称首次无问题。

[运行证据](evidence/2026-10-20-cost-report-repair/release.safe.json)、[独立证据](evidence/2026-10-20-cost-report-repair/release-independent.safe.json)、[原有限契约](COST_REPORT_ORDER_REPAIR.md)。

## Oct20：计费修复发布原文已登记，当前十二项独立职责

本批起点2026-10-20 02:26:52.661740UTC，原期限 **2026-10-27 02:26:52.661740UTC**（1793068012.66174）；最终446 CAPTURED/0 NOT_CREATED，ledger SHA `02a9e2bbb65da1dab9f5af28f5cf79022109e439c14e4678cbda5b704a592115`。基线/配置/模板/发布/API及恢复读回全部同一期限，0600/0700；ZIP/纯源码/安全聚合保留。当前SOURCE此前已登记E2/F5字段，旧9项摘要属当时阶段，以本十二项为准。

| UTC原期限 | 实际职责 |
| --- | --- |
| Oct20 14:32:29.705948 | 告警341，准备完成，尚未删除 |
| Oct21 13:10:50.198516 | 首发527，准备完成，尚未删除 |
| Oct24 16:20:38.287378 | PITR读回H10 |
| Oct24 16:29:48.470834 | 首发观察O51，独立于H |
| Oct26 20:29:05.508343 | PR277发布418 |
| Oct26 23:52:42.922982 | 媒体停止N36 |
| Oct27 00:10:10.807865 | 元数据诊断D22 |
| Oct27 01:53:25.893115 | worker日志读回E2 |
| Oct27 01:57:25.452039 | 指标/原query F5=原3+窄续接2，同一原期限 |
| Oct27 02:26:52.661740 | 本批发布及正常恢复读回446，按最终ledger |
| Nov1 11:46:02.425 | 旧memory SYSTEM原身份只读 |
| Nov2 08:45:11.254 | 旧stats SYSTEM原身份只读 |

每项原路径/hash/身份/期限保持，未到期不提前apply；另新精确scope/双PRE/公告/到期逐文件删除与独审，UNKNOWN保全，不重建已删除原文。今日告警341期限优先，履行后原heartbeat重排下一期限前60分钟内。普通unlink非安全擦盘；用户导出/现役PITR/必要恢复保留。45ZIP此前保留不表示永久不能删除，询问用途未扩大删除范围。

两次 AWS 观测水位均为 1792465708，早于本次 prod Execute 完成 1792465760.097933，不能据此判断新代码定时运行失败或已经恢复。

本地汇总首次因安全 PRE 的 ISO 时间格式被数值门禁拒绝，未生成 final、无新云操作；原工具/双 PRE/once/intent/失败共八文件保全。仅四个精确冻结 PRE 允许 ISO UTC 解析的新续接经 33 正确性/25 维护控制后唯一完成，实际完整链另独审通过；运行时间门禁不变。

## 以下为此前冻结阶段；其当前包、未发布或待核摘要仅属当时，不作重跑指令

## Oct20：媒体验收发送前停止；共享成本门缺覆盖，继续有限诊断

用户本次给出新的15分钟Telegram独占，并单独授权清掉Test bots输入框的一个空格；主现场核了账号、唯一dev群与@zerde_dev_bot，清理后输入框为空。原生UI为主观察，数字身份来自原绑定，不称独立UI或原生取得消息ID。现场preflight31只读通过，但预算reader第4读按原owner抛MemoryBudgetPaused；未上传图片、未发送相册或提问、无模型调用/预算预留，窗口已提前释放，不借余下时间或旧STOP续跑。所有本批once冻结，媒体业务验收仍未完成。

该dev入口读取的是共享prod Memory V2表中的项目预算，并非dev独立钱包。实际AWS成本行UNVERIFIED/UnverifiedCost、covered_until=0、valid_until已失效；paused=false、估算低于停止阈值，所以不是额度耗尽。原冻结stop回执的dev_only_observed只指业务入口，不代表独立dev预算；未fresh核生产群状态或断言整个Bot停用。

新有限诊断严格22AWS只读：STS1、原成本owner资源元数据20、共享预算表当月DAY精确强一致单页1。当前全部资源门通过；33行无续页，按原12小时/900秒settled窗口复算为32块完整、5块缺席、1块覆盖不足、0错inventory，最早缺口2026-10-17 00:00UTC。当前缺口能解释许可不足，**原23:08监控UnverifiedCost的具体抛错分支仍UNKNOWN**；当前资源通过不能倒推历史通过，也不能用缺口直接认定原异常原因。没有日志扫描、手动Invoke、模型、预算写入或阈值/epoch改动；下一步仅围绕缺口的失败计量证据作新有限诊断，不重跑旧reader或手工补许可。

两批合计57操作器AWS只读、0云写/模型/预留/运行发布；58原文=现场N36（1UI+31+4API）和诊断D22。两个独立七日期限分别Oct26 23:52:42.922982UTC、Oct27 00:10:10.807865UTC，原其它七项期限保持，共九项。四群RELEASED_OBSERVING发布事实、自然0/50有据0/20未知/起点null和20任务14OPEN6CLOSED/EpicOPEN保持；本轮未重新证明生产业务或自然质量。

[本次停止及诊断契约](MEDIA_BUDGET_STOP.md)、[实际停止](evidence/2026-10-20-media-budget-stop/media-stop.safe.json)、[停止独审](evidence/2026-10-20-media-budget-stop/media-independent.safe.json)、[诊断结果](evidence/2026-10-20-media-budget-stop/diagnostic.safe.json)、[精确副本职责](RETAINED_COPIES.md)。

## 以下为此前完整阶段，仅历史；旧窗口、待执行和绑定状态不作重跑指令

## Oct20：当前运行包的相册验收准备完成，等待新独占窗口

已将两图相册/caption/原生Reply验收工具绑定PR277当前Bot/Memory、PR263 Operations与PR251身份配置。主独12个完整ZIP与104个源码文件一致；其中98项保持、6项为已发布的反垃圾修复，五个Memory计费owner不变。原五个媒体模块字节保持，原业务验收标准不降低。

新七工具通过计划、正确性与维护独审；78主离线控制（76+2差异）、34独立差异控制和87维护有限控制通过。已修窗口过期/读取与写入前期限/表声明配置及一次入口留证缺口，旧草稿、失败与修订保全；-O、非法label和首次claim失败属于零动作入口拒绝，不保证创建内部回执。只有合法新label成功claim后的PRE/绑定/操作异常纳入内部once留证。

现场 **NOT_EXECUTED**：尚无新的直接人类独占确认，未打开Telegram、读取实际私有快照、执行云preflight/预算时点读取、上传发送或调用模型，无新原文期限/自然样本。唯一候选为dev Test bots中两张合成图，双ready后360秒静默，再原生Reply caption父图提问；必须取得完整两图Gemini链、可见语义、单SENT回答/RELEASED lease与独立POST。旧S快照已删除，不重建；新B依赖仍受原Oct26期限限制。

[有限契约](Z01_MEDIA_CURRENT_ACCEPTANCE.md)、[准备聚合](evidence/2026-10-20-z01-media-current/preparation.safe.json)。Z01/Epic保持OPEN，其他19任务对象与全部状态、四群RELEASED_OBSERVING、自然0/50有据0/20未知及七项副本职责均保持。源码/文档发布不代替现场媒体通过，不产生新运行构建。

## 以下为此前完整冻结阶段；旧绑定与未完成表述不作当前许可或重跑指令

## Oct20：Groq 413 未分类审核保护已部署 dev/prod

运行构建源 `341d2e3d7020b4cd1d6730e65456194bf246a0b7`（PR277），Bot/Memory 两环境实际完整ZIP均为 `5a0227ab654c462c53c83c187a676d8c623686046d27a483573dcf99496890d2`。每环境唯一 Execute 已完成，主、独分别下载核对五函数和共享层，且原 Execute 后均至少300秒完成配置/保护稳定读回；dev 570.415229秒、prod 1084.167275秒。News、Quiz、Operations和共享层原包、身份配置、四群CONTROL稳定字段/合法revision及8项prod日程保持。本文的运行SOURCE与后续文档HEAD/merge分别记录，文档合并不会另触发部署。

明确收到413后，在原owner/lease内持久保留“未分类、待人工审核”；持久化后的重投不再请求模型，不自动CLEAN、学习、删除或封禁。通知ATTEMPTED/UNKNOWN不自动重发，只有明确确认才SENT。普通用户/有效guest caller沿原管理员审核，guest文案区分机器人和调用者；无有效个人caller不提供处罚按钮，服务端也拒绝伪造action。初次413到持久化之间仍有失败间隙，不宣称严格一次；原30日case TTL、模型/prompt/共享SDK、五Memory计费owner及epoch/DAY/UNKNOWN不变。

83项最终定向测试、2519项全测（其后仅四语言处罚提示与对应断言调整）及源码CI三job通过，两环境实际ARM五入口/8项合成探针通过；不算真实413或Telegram人工审核验收。供应商具体数值限制仍UNKNOWN。原candidate ZIP元数据失败/独审误停保全；prod首次post仅31metadata/layer读后0ZIP/0snapshot断言停，原无栈原因UNKNOWN。新只读V5仅接受两个既有QuizRule模板Description的精确Mon–Fri/Mon?Fri读回差异，实际规则/target保持，原失败不重跑、无第二Execute。工具时钟/路径/原文门禁与harness修订全部保全，不宣称首次无问题。

本批操作器实际AWS 374次（含原失败31读），其中云写8次=4 PutObject+2 CreateChangeSet+2 ExecuteChangeSet；运行阶段GitHub GET32次，后续文档发布/CI读取另计。0主动模型/UI/自然样本；生产正常业务的调用不归入该操作器计数。四群仍RELEASED_OBSERVING，自然0/50有据、0/20未知、起点null、production_ready=false；20工单14OPEN/6CLOSED和EpicOPEN保持；其余16个manifest对象保持原阶段记录，不代表本轮重验或当前包来源。新整体Bot/Memory包使此前R及旧S/Z完整聚合许可不能继续复用；后续模型/媒体须按当前包和原owner/期限重新有限绑定独审，旧S snapshot不重建。

[运行证据](evidence/2026-10-20-groq-413-review/release.safe.json)、[独立证据](evidence/2026-10-20-groq-413-review/release-independent.safe.json)、[有限契约](GROQ_413_REVIEW.md)。

## Oct20：新增 Groq 413 发布原文责任，现共七项

本批首次真实API意图起点2026-10-19 20:29:05.508343UTC，固定七日期限 **2026-10-26 20:29:05.508343UTC**（epoch1793046545.508343）。最终实际 **418 CAPTURED/0 NOT_CREATED**，原ledger SHA `eccbecaac4db0bbdc7b9513dbe411f669410c74b75529c2aa936bce9af038318`；原文和含原文派生同一期限，0600/目录0700，完整ZIP/纯源码/安全聚合保留。原prod失败31份也已登记，不按成功汇总遗漏或延长。逐文件新scope/PRE/公告、到期唯一删除及独审另行执行；本次不删原文。

| UTC原期限 | 职责 |
| --- | --- |
| Oct20 14:32:29.705948 | 告警341，独立准备已完成未删 |
| Oct21 13:10:50.198516 | 首发527，独立准备已完成未删 |
| Oct24 16:20:38.287378 | PITR核验原文10 |
| Oct24 16:29:48.470834 | 首发观察原文51，与前项不合并 |
| Oct26 20:29:05.508343 | 本批Groq 413发布418，按最终ledger完整路径 |
| Nov1 11:46:02.425 | 旧memory SYSTEM原身份到期只读 |
| Nov2 08:45:11.254 | 旧stats SYSTEM原身份到期只读 |

前六项原路径/hash/身份/期限完整保持。原zerde每日阿拉木图19:05先覆盖Oct20，履行后重排下一期限前60分钟内；每次真实延误如实记UNKNOWN，不改期限。已履行旧清理不重跑，普通unlink非安全擦盘；用户导出/现役PITR/必要恢复保留。45ZIP此前明确保留不等于永久不可删，用户询问用途未扩大删除授权。[运行证据](evidence/2026-10-20-groq-413-review/release.safe.json)。

## 以下为此前冻结阶段；其未部署、数量和绑定描述不作当前状态或重跑指令

## Oct20：Groq 413 审核失败处理已完成本地修复，待CI及运行发布

已明确收到HTTP413的反垃圾case持久保留为未分类审核，重投不再次调用模型、不自动CLEAN/学习或处罚；通知发送未知不自动重发，已送达通知可沿原管理员按钮处理。guest明确显示机器人和调用者，并说明永久封禁目标；无有效个人caller不提供处罚按钮，服务端也拒绝伪造action。模型、阈值、共享计费owner和供应商具体限制UNKNOWN保持。

83项最终定向测试通过；2519项全测通过后仅补四语言永久处罚提示与对应断言，最终CI仍待。原独审发现的两处真实缺口已修、失败和测试隔离误停保全。当前无新AWS/UI/模型调用、未合并/未部署，不代替真实业务或自然验收。四群已发布状态、长期观察、六项到期责任及20任务14OPEN/6CLOSED保持。

[有限契约](GROQ_413_REVIEW.md)；[本地证据](evidence/2026-10-20-groq-413-review/local.safe.json)。

## 以下为此前冻结阶段；其历史状态不作本轮重跑指令

## Oct21 首发527原文清理已准备，尚未删除

原期限 **2026-10-21 13:10:50.198516 UTC** 的最终527项原ledger相对完整路径已完成新工具双审、主唯一inspect Prep20261019A及独立fresh无跟随hash/身份/前后库存核验。全库存910常规文件，383保留、7目录（3个0700、4个0755），没有链接或ZIP。41个保护文件另有精确历史hash，342个仅本次fresh基线；原目录模式保持，目标全部祖先0700。

原根与completion两份automation-before.private.toml经原创建call/exit0追溯为行政历史；根write_bytes不是独占创建且无原整文件hash，completion为xb并有原hash，不能混称。保留不等于内容无敏感。原首发final465和publisher512为阶段，最终独审与ledger是527，原起点Oct14 13:10:50.198516UTC与七日期限不变。

本轮没有notice/apply/verify_absence或删除。到期另new inspect/原序公告，原hash身份完整库存保持才唯一apply，1054条intent/result、双侧unlink_returned/absent严格True与独立fresh不存在。Oct20告警341另批准备已完成未删；其余Oct24两期限、Nov1/Nov2原SYSTEM只读职责保持，共六项，不合并或延期。原zerde每日阿拉木图19:05先覆盖Oct20，履行后必须重排Oct21到期前60分钟内。

四群仍RELEASED_OBSERVING，Oct17有限观察已交付，Oct21首周观察另有限合同；自然0/50有据、0/20未知、起点null及production_ready=false保持。20任务14OPEN6CLOSED+EpicOPEN。原失败/UI_STOP/UNKNOWN/历史费用及已结束once冻结。旧S snapshot不重建；运行包不变。本地准备0云/UI/模型/新原文/预算/运行发布，无新增期限；CI既有OIDC/CDK只读另计。[契约](LAUNCH_RAW_EXPIRY.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、绑定或重跑指令

## Oct20 告警诊断原文清理已准备，尚未删除

原期限 **2026-10-20 14:32:29.705948 UTC** 的341个原ledger完整路径已完成新工具双审、主唯一inspect Prep20261018A及独立fresh无跟随hash/身份/前后库存准备。保护30980个常规文件（含39 ZIP）、1个精确链接及8938目录；共31322文件系统条目，其中31321为常规文件。39 ZIP另与原safe回执历史hash一致，其余30941保留常规文件仅本次fresh基线。原44个0700/8894个0755目录身份保持，不擅自chmod或称全部cache。

唯一链接diff-v2-dev/assembly/stack.template.json指向本次candidate-dev/template.private.json目标，保留link本体lstat/readlink，绝不跟随；到期删除目标后将悬空。alarm-summary.safe.json虽然safe后缀仍是登记原文目标。原automation-before.private.toml有创建调用/exit0行政来源，保留不等于无敏感内容。

本轮没有notice/apply/verify_absence或删除。到期另new inspect/原序公告、原hash身份完整库存保持才唯一apply，682条intent/result、双侧strictTrue与独立fresh不存在。全部原截止时间不变：Oct20告警341、Oct21首发527、Oct24 16:20:38.287378UTC H10、Oct24 16:29:48.470834UTC O51、Nov1旧memory SYSTEM、Nov2旧stats SYSTEM。旧S snapshot及所有已履行批次不重建/重跑。

四群仍RELEASED_OBSERVING，Oct17有限观察已交付，Oct21首周继续；自然0/50有据、0/20未知、起点null和production_ready=false保持。20任务14OPEN6CLOSED+EpicOPEN，运行包/告警策略/Groq413与费用UNKNOWN不变。本地准备0云/UI/模型/预算/新原文/新期限/运行部署，CI既有OIDC/CDK只读另计。[契约](ALERT_RAW_EXPIRY.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、绑定或重跑指令

## 2026-10-17：四群首发后观察和旧 PITR 到期复核已完成

四群 Memory V2 均 ACTIVE、learning=true、首发 epoch 保持；第四群 News Oct15–17 每天4个已保存步骤有 SENT 回执，Quiz Oct15–16 为 DONE 并有发送回执。独立 fresh 覆盖四 CONTROL 和 Oct15 News/Quiz；其他页为主读取后独立离线核验。未看原生 Telegram、完整答案语义、完整 News 清单或 Quiz 三行一致性；周榜未覆盖。自然仍 0/50 有据、0/20 未知，起点未建立、production_ready=false，RELEASED_OBSERVING 不变。

旧 memory 原 PITR 期限 Oct17 16:20:38UTC 已在到期后按原身份主独复核：旧表及 PITR 入口不存在，窗口字段不可取得；SYSTEM 备份仍 AVAILABLE，Nov1 原期限不变。主首次 API 意图晚0.287728秒，原因 UNKNOWN；不是所有副本消失或物理擦除。H 主5+独5读，O 原失败26+窄续接15+独10读，共61 AWS只读，0云写/UI/模型/部署。原空 epoch 门禁失败冻结，25条首发前旧答案归UNKNOWN，不算当前答案或自然样本。8个返回页中3页有续页，不能推全量积压。

当前剩余6项副本责任，包含本次 H10/O51 两个独立新七日期限。下一观察 Oct21，之后每周；完整边界与证据见[Oct17回执](OCT17_READBACK.md)，精确期限见[副本台账](RETAINED_COPIES.md)。20任务14OPEN/6CLOSED、Epic OPEN；独立业务/费用缺口保持，所有已结束入口不重跑。

## 以下为此前阶段记录，不作当前待办、数量、现场许可或重跑指令

## 2026-10-16：四群已发布，writer 原文 1426 份到期责任已履行

Memory V2 四个生产群保持 RELEASED_OBSERVING；dev 学习/回答/定点遗忘/删除后查询及生产激活独审已完成，第四群 News/Quiz/周榜配置已交付。自然 0/50 有据、0/20 未知、起点未建立、production_ready=false；Oct17、Oct21 及之后每周有限观察，首次正常定时投递仍待观察。运行包仍 Bot/Memory PR257、Operations PR263，身份 PR251。开放工单数不表示首发未启用。

原 ledger 的 1426 个完整路径已逐项移除并独立 fresh 核不存在；95425 保留文件（含 45 完整 ZIP）hash/身份、27812 目录原身份/模式及 96851→95425 库存保持。2852 条 intent/result、公告和五 hash 一致，apply/journal 两侧 unlink_returned/absent 严格 True。原期限 2026-10-16 18:48:47.827167UTC 不变；实际首末 unlink 2026-10-16T18:49:13.441939+00:00 / 2026-10-16T18:49:13.995025+00:00，真实晚 25.614772 至 26.167858 秒，原因 UNKNOWN。原 0700/0755/0777 目录分别 13780/14020/12，非全部 cache；25 非目标 private 行政历史按 scope 保留。原失败、UNKNOWN、ledger 和历史报告不改。文件移除非安全擦盘或所有云副本消失；本地清理 0 云/UI/模型/新原文/运行部署，37 在线退役数不增。Due20261016A、Apply20261016A、独立 verify 均结束不可重跑；原 snapshot 不复制、延长或重建。

剩余 5 项原精确 UTC 责任：Oct17 16:20:38 旧 memory PITR；Oct20 14:32:29.705948 告警 341；Oct21 13:10:50.198516 首发最终 527；Nov1 11:46:02.425 旧 memory SYSTEM；Nov2 08:45:11.254 旧 stats SYSTEM。原身份、期限及用户导出/现役 PITR/必要恢复保护保持。20 任务 14 OPEN/6 CLOSED、Epic OPEN。计划将原 heartbeat 调整为每日 Almaty 21:05=16:05UTC，覆盖 Oct17 PITR 前 938 秒；实际设置以 automation 回执为准。逐批再安排下一期限前不超过 60 分钟唤醒，不保证设备准时执行。

[完成证据](evidence/2026-10-16-writer-raw-expiry/completion.safe.json)、[独立不存在](evidence/2026-10-16-writer-raw-expiry/completion-independent.safe.json)、[副本台账](RETAINED_COPIES.md)、[首发进度](LAUNCH_PROGRESS.md)。完整前阶段见[PR272 固定基线](https://github.com/Bayashat/zerde-serverless-bot/blob/0589e61732c6d131b64ee92a67efae1c4cd12646/docs/goals/zerdebot-memory-v2/PLAN.md)。

## 以下为此前冻结阶段，不作当前首发顺序、现场许可或重跑指令

## Oct16 shared writer 原文清理已准备，尚未删除

原期限 **2026-10-16 18:48:47.827167 UTC** 的1426份账本目标已完成新工具双PRE、主唯一inspect Prep20261015A及独立fresh无跟随流式hash/身份/前后完整库存核验。95,425个保留文件（含45个ZIP）、27,812个目录保持，完整库存96,851文件；原目录权限逐路径保留，0755及12个0777资产根不改称全部cache。64,429个保护项另与已证历史hash一致，其余30,996个建立本次fresh基线；candidate不套canonical旧hash。范围SHA `9066fbf3ca1ba7e00403478801a7e6927c81f4d648ce1e26cf3a7890a2c8c48c`。

apply、公告及独立不存在核验均未执行。到期当轮另新inspect/精确公告，原hash/身份/全库存保持才唯一apply；预期2852条intent/result，双侧unlink_returned/absent严格True，逐项intent距公告<=3600秒，再独立fresh不存在。未知保全partial另窄续接，不重apply或复制/重建/延长原snapshot。文件移除非安全擦盘。

六项原UTC责任仍是Oct16 18:48:47.827167、Oct17 16:20:38、Oct20 14:32:29.705948、Oct21 13:10:50.198516、Nov1 11:46:02.425、Nov2 08:45:11.254。此前85/128/1030等已履行不重做。四群Memory仍RELEASED_OBSERVING，Oct17/21发布后观察；自然0/50有据、0/20未知和20任务14OPEN6CLOSED保持。运行包/定时配置/Groq413与费用UNKNOWN不变；本批0云/UI/模型/删除/新原文/新期限或运行部署，CI既有只读另计。

[本批契约](WRITER_RAW_EXPIRY.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、绑定或重跑指令

## 2026-10-15：四群已发布，提及与Reply原文85份到期责任已履行

Memory V2四个生产群保持 **RELEASED_OBSERVING**；dev学习/回答/定点遗忘/删除后查询与生产激活独审已完成，第四群News/Quiz/周榜配置已交付。运行包仍Bot/Memory257、Operations263，身份251。自然0/50有据、0/20未知、起点未建立、production_ready=false；Oct17、Oct21及之后每周有限观察，首次正常定时投递尚待观察。开放工单数不代表首发未启用。

提及与Reply原文85个原ledger完整路径已逐项移除并独立fresh核不存在；103保留文件哈希/身份、6目录原0700及188→103库存保持。170条intent/result、公告和五hash一致，apply/journal两侧unlink_returned与absent严格True。原期限08:17:52.186798UTC保持；首末unlink 2026-10-15T08:17:52.309755+00:00 至 2026-10-15T08:17:52.360509+00:00，真实晚0.122957至0.173711秒，原因UNKNOWN。原M/R有限PASS、俄文问题中文答案、UI证据限制及共享计数UNKNOWN保留，7份非目标private历史按scope保护。文件移除非安全擦盘/所有云副本消失；0云/UI/模型/新原文/运行部署，37在线退役数不增。Due20261015A/Apply20261015A/独立verify均已结束不可重跑。较早公开128和配置1030亦已履行。

当前剩余6项精确UTC职责：Oct16 18:48:47.827167 writer1426；Oct17 16:20:38旧memory PITR；Oct20 14:32:29.705948告警341；Oct21 13:10:50.198516首发527；Nov1 11:46:02.425旧memory SYSTEM；Nov2 08:45:11.254旧stats SYSTEM。原身份、期限与保护保持，20任务14OPEN/6CLOSED、EpicOPEN。计划将原heartbeat调整为每日23:35Almaty=18:35UTC，覆盖最近Oct16期限提前827.827167秒；实际设置以automation回执为准。未来逐批调整下一期限前不超过60分钟唤醒，不保证设备必然准时。

[本批完成证据](evidence/2026-10-15-mention-reply-raw-expiry/completion.safe.json)、[独立不存在](evidence/2026-10-15-mention-reply-raw-expiry/completion-independent.safe.json)、[副本台账](RETAINED_COPIES.md)、[首发进度](LAUNCH_PROGRESS.md)。完整前阶段见[PR270摘要](https://github.com/Bayashat/zerde-serverless-bot/blob/18c99dd54373ca8e3436bf781410b0eb348151df/docs/goals/zerdebot-memory-v2/PLAN.md)。

## 以下为此前冻结阶段，不作当前首发顺序、现场许可或重跑指令

## Oct15 提及与 Reply 原文已准备，尚未删除

原期限 2026-10-15 08:17:52.186798 UTC 的 85 个账本路径已完成双工具 PRE、主唯一 inspect Prep20261014A 和独立 fresh 无跟随 hash/身份/前后库存核验；103 保留、6 目录全部 0700、188 全库存固定。85 是 61 根 API + 7 UI + 17 独立 API，不用旧 29/68，也不再加入外部预算读。7 个非目标 private 历史已核来源并保留。apply、verify_absence 和 notice 均未执行；准备不等于删除。

到期另新 inspect、精确公告、原 hash/身份/库存、唯一 apply 和独立不存在；公告距逐项 intent <=3600 秒，预期 170 journal，双侧 unlink_returned/absent 严格 True。未知保全 partial 另窄续接，不重 apply/重建。原 M/R 有限 PASS、UI/语言/共享计数限制、失败和 UNKNOWN 保持，旧输入不复做。

今晚 Oct14 20:45:55.665021 的公开128和21:48:46.021161的配置1030仍各自准备完成尚未删；本批不运行它们的入口。其余 Oct16/17/20 和 Nov1/2 原期限保持，共八项。文件移除非安全擦盘，用户导出/现役 PITR 保留，37 在线退役数不增。本地准备 0 云/UI/模型/删除/新原文或期限，CI 既有只读另计。Operations263/Bot-Memory257/身份251不变，旧 S/Z 须重绑，无 Telegram 新独占窗口；自然0/50有据0/20未知、production_ready=false，20任务14OPEN6CLOSED及EpicOPEN保持。

[本批契约](MENTION_REPLY_RAW_EXPIRY.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、绑定或重跑指令

## Oct14 两批原文清理已分别完成准备，尚未删除

公开文本128份的原期限为2026-10-14 20:45:55.665021UTC，配置发布1030份为21:48:46.021161UTC，两时点独立。新工具正确性/维护PRE、主唯一inspect和独立fresh无跟随hash/身份核验通过：前批68保留/5目录/196库存，后批310保留/37目录/1340库存（含24个保留ZIP）。准备label Prep20261013A各自已结束；apply/verify_absence/notice均未执行，不把准备当已删。

配置1030同时含95迁移失败和后来成功的账本路径，必须按完整当前路径，不按previous_path、basename或后缀误删；N的登记审计源派生包含在128内。原失败/STOP/晚登记偏差、ledger和UNKNOWN保持，原目录模式逐路径保持；G的pre-controls原为0755，不将其误称cache。到期另新inspect/精确公告/原hash身份库存/唯一apply/独立不存在；每项intent距真实公告<=3600秒，早到每次<=60秒等，不提前或故意拖晚，未知保全partial另窄续接。

本地准备0云/UI/模型/删除/新原文，顺序核验非事务；文件移除非安全擦盘，用户导出/现役PITR保留。八项原期限仍见台账，已完成清理不重删重建，37在线对象不增。Operations PR263、Bot/Memory PR257、身份PR251保持，旧S/Z聚合许可失效，未来reader/媒体须另窄重绑；无Telegram独占确认，不启动现场。20任务14OPEN6CLOSED、Epic OPEN、自然0/50有据0/20未知和production_ready=false保持。

[公开文本清理契约](PUBLIC_TEXT_RAW_EXPIRY.md)；[配置原文清理契约](IDENTITY_RAW_EXPIRY.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、绑定或重跑指令

## 2026-10-13晚次：四份迁移失败原文清理已独审完成

原期限18:26:43.519150 UTC保持。两迁移ledger的4精确文件（3份元数据和一个空[]记录，不是4份AWS响应）已移除；首末unlink为2026-10-13T18:26:43.630886+00:00、2026-10-13T18:26:43.632391+00:00，真实晚0.111736至0.113241秒，原因UNKNOWN。独立fresh核4路径不存在、12保留hash/身份、5目录和两失败archive剩余6文件；成功轮四个同名原路径及2ZIP保持。8条intent/result、公告和五hash绑定一致，apply与journal各自unlink_returned/absent均严格True。

原失败、ledger、安全聚合和费用UNKNOWN保持，未恢复原文/补采集；清理本地0云/UI/模型/新原文/运行部署。文件移除不是安全擦盘或所有云副本消失，顺序核验非事务；用户导出/现役PITR保留，37在线退役计数不增。旧准备和唯一Due20261013B、Apply20261013B、verify均已结束不可重跑。

剩余8项UTC责任：Oct14 20:45:55.665021公开128；Oct14 21:48:46.021161配置1030；Oct15 08:17:52.186798 M/R85；Oct16 18:48:47.827167 writer1426；Oct17 16:20:38 PITR；Nov1 11:46:02.425 memory SYSTEM；Nov2 08:45:11.254 stats SYSTEM；Oct20 14:32:29.705948告警341。原期限/逐文件身份不变，Oct14两时点不合并，已履行项不重删重建。

Bot/Memory运行PR257和PR251身份配置保持；Operations及prod告警已由PR263发布，源码f049f6856f990c8ec2d997558f1c4d482a1dbca9。dev DisableRollback true→false已按窄合同接受、prodtrue保持；Groq413具体限制UNKNOWN。旧S/Z完整聚合绑定失效，未来reader/media须另窄重绑独审，仍无Telegram独占窗口。本批无新业务/自然验收；20任务14OPEN/6CLOSED、Epic OPEN，自然0/50有据0/20未知、production_ready=false保持。

[清理契约](FAILED_READBACK_RAW_EXPIRY.md)；[完成聚合](evidence/2026-10-13-failed-readback-raw-expiry/completion.safe.json)；[独立不存在](evidence/2026-10-13-failed-readback-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删、运行绑定或重跑指令

## 2026-10-13：三份发票原文清理已独审完成

原期限08:06:04.659429 UTC保持。两份invoice ledger绑定的3个精确文件已移除；首次/末次unlink为2026-10-13T08:06:04.740853+00:00、2026-10-13T08:06:04.742064+00:00，实际晚0.081424至0.082635秒，原因UNKNOWN。独立重新核三个路径不存在、83保留文件hash、7目录身份及剩余库存，6条intent/result与公告、五项hash绑定和时间链一致，unlink_returned均严格为True。原cache模式保持。

两份ledger、原失败、费用结论和UNKNOWN保留；账号摘要38.65+6.18=44.83不变，非项目独占/付款/完整FreeTier，CE差0.0074992985原因仍UNKNOWN。清理及本地核验0云/UI/模型/新原文/运行部署；CI既有OIDC/CDK只读另计。文件移除不是安全擦盘或所有云副本消失，顺序读取不是全局事务，37在线退役数不增。

剩余8项UTC责任：Oct13 18:26:43.519150失败4；Oct14 20:45:55.665021公开文本128和21:48:46.021161配置1030；Oct15 08:17:52.186798 M/R85；Oct16 18:48:47.827167共享writer1426；Oct17 16:20:38 PITR；Nov1 11:46:02.425旧memory SYSTEM；Nov2 08:45:11.254旧stats SYSTEM。各批不合并、原期限不延长；已履行项不重删重建，用户导出/现役PITR保留。

相册Z已完成PR257/PR251/S reader五工具重绑准备，仍待直接人类确认新15分钟Telegram独占窗口；未启动现场或新期限。运行PR257、配置PR251、S reader与五费用owner保持。Z10/Z17/Epic仍OPEN；20任务14OPEN/6CLOSED、自然0/50有据0/20未知、production_ready=false保持。

[清理契约](INVOICE_RAW_EXPIRY.md)；[完成聚合](evidence/2026-10-13-invoice-raw-expiry/completion.safe.json)；[独立不存在](evidence/2026-10-13-invoice-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删或重跑指令

## 2026-10-12：相册验收已重新绑定当前包，尚未开始现场动作

新的相册批次已将有限计划、五工具和独立核验绑定 PR257 实际包、PR251 配置及 S 当前预算 reader/纯校验模块；19份发布回执与104个费用相关源文件已核对。五个媒体处理模块字节未变，保留原两张合成图片与成功标准。77项主离线控制、54项独立控制及正确性/维护PRE通过；这些是准备证据，不是媒体业务通过。

仍等待用户确认新的约15分钟Telegram独占窗口。此次没有打开Telegram、云preflight、预算时点读取、上传/发送、模型调用或新原文期限。首次现场采集前须建立新批七日原文账本，初始账号/群/空草稿观察也纳入同一期限。S旧快照仅可在原Oct16 18:48:47.827167UTC期限内使用；读取前后都校验期限，不复制或延期，届时缺失须新有限合同。旧Y准备与H/N的STOP永久保留。

原合同仍是两图同相册、两个真实鉴权输入与双ready后360秒静默，再一次对caption父图的原生Reply ask；完整两图模型应用链、答案语义、SENT单回答与lease释放及独立POST均待实际发生。独审发现跨期限读快照及窗口校验顺序缺口，均已修并保全旧源与报告；本地临时路径测试失败也保留，不冒称首次全通过。

运行/配置/五Memory费用owner保持，文档提交不发布Lambda。原九项期限不变，最近Oct13 08:06:04.659429UTC发票3与18:26:43.519150UTC失败记录4分别到期；两批仅准备完成。Oct12答案247、Oct11费用9及此前已履行项不重删重建。20任务14OPEN/6CLOSED、Epic OPEN、自然0/50有据0/20未知、production_ready=false保持。准备本地0云，后续CI既有OIDC/CDK只读另计。

[本批有限合同](Z01_MEDIA_REBIND_ACCEPTANCE.md)；[准备回执](evidence/2026-10-12-z01-media-rebind/preparation.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待做或重跑指令

## 2026-10-12：247份答案原文清理已独审完成

原期限2026-10-12 17:15:22.532382UTC不变。247个精确文件（246份private JSON及含原文click-intent.safe.json）已逐项移除；首次/末次unlink为2026-10-12T17:15:22.647203+00:00、2026-10-12T17:15:22.983452+00:00，实际晚0.114821至0.451070秒，原因UNKNOWN，不改写为提前或绝对准时。独立重新lstat全部目标不存在、217保留hash/18目录身份及剩余库存保持，494条intent/result与公告、原ledger和时间链一致。原__pycache__0755保留。

原PARTIAL_UNCONFIRMED_UI、旧STOP/失败/安全聚合和原ledger保持；清理不证明投票提交、HTTP500重送或一次计分通过，不重发/重答旧题。文件移除不是安全擦盘或所有云/外部副本消失，顺序核验不是文件系统事务。清理和本地核验0云/UI/模型、新原文或运行部署；后续CI既有OIDC/CDK只读另计。

剩余九项责任：Oct13早次发票3、晚次旧PR248失败4；Oct14早次公开文本128、晚次配置1030；Oct15提及Reply85；Oct16共享writer1426；Oct17 PITR；Nov1旧memory SYSTEM；Nov2旧stats SYSTEM。各原精确期限见副本台账，不合并双时点。Oct11费用/Oct8日志/USER/AV/三归档key已履行且真实延误保留，不重删重建；用户导出、现役PITR和必要恢复保留。

运行PR257/配置PR251/S reader保持。Z10/Z16/Epic继续OPEN，20任务14OPEN/6CLOSED、自然0/50有据0/20未知及production_ready=false不变；相册仍待新包重绑和新的Telegram独占窗口，未操作UI。

[清理契约](QUIZ_ANSWER_RAW_EXPIRY.md)；[实际聚合](evidence/2026-10-12-quiz-answer-raw-expiry/completion.safe.json)；[独立不存在](evidence/2026-10-12-quiz-answer-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

### Oct13早、晚两批只完成准备

次日08:06:04.659429UTC发票3份已双PRE、主inspect及独立fresh核验：83保留hash/7目录/86库存保持；V2沿原更早期限。18:26:43.519150UTC失败读回4份亦完成双PRE、主inspect和独立fresh核验：12保留hash/5固定目录身份、两失败archive10文件完整；成功轮四同名路径保持，不使用旧previous_path删除。两批仅准备，apply/verify_absence均未执行，原时点分开、没有新增原文或期限。

发票新工具V1负控发现未强制unlink_returned=true，已窄修严格门禁并保留原意见/工具；失败4主wrapper首轮因PRE状态全名误读在入口前停，修正读取schema后唯一inspect通过，原停止记录保留。这些本地准备记录不改旧业务FAIL/UNKNOWN或已删事实。

[发票三文件契约](INVOICE_RAW_EXPIRY.md)；[失败读回四文件契约](FAILED_READBACK_RAW_EXPIRY.md)。到期另新label inspect/精确公告/hash身份/一次apply及独立不存在；准备label Prep20261012A已结束不能重用。

## 以下为此前冻结阶段，不作当前待删或重跑指令

## 2026-10-11：九月费用九份原文已删除，真实迟延保留

原期限2026-10-11 17:01:48.147210UTC不变。九个精确文件实际首次/末次unlink为2026-10-11T21:20:31.636119+00:00和2026-10-11T21:20:31.639021+00:00，分别晚15523.488909秒和15523.491811秒（约4小时18分43秒）。本轮首次实际时钟检查已经晚于期限，后续执行间隔原因UNKNOWN，不猜测设备或调度原因，不改写为按时完成。

唯一apply与独立不存在核验均完成：6份AWS原始响应、2份Google CSV和1份UI观察已移除；57份列明保留文件hash、6目录身份和37个未创建槽保持，18条逐项intent/result与公告、原ledger和实际时点一致。raw/007–043从未创建，不算已删；安全费用聚合、旧失败、原账本和全部费用UNKNOWN保留，原37在线对象计数不增。文件移除不是安全擦盘或所有云/外部副本消失。

本清理/核验0云API、UI、模型或新运行部署，后续CI既有OIDC/CDK只读预览另计。运行仍PR257字节、PR251配置，唯一时点reader仍共享writer批次S；本轮不重复任何旧reader/采集/发布。剩余十项职责中最近是Oct12 17:15:22.532382UTC答案原文247文件，其准备已完成，apply尚未执行；Oct13/14各双时点及Oct15/16/17/Nov1/Nov2保持。用户导出、现役PITR和必要恢复数据保留。

Z10/Z17/Epic继续OPEN，20任务14OPEN/6CLOSED保持，自然0/50有据、0/20未知，production_ready=false。相册尚未重绑定新包，也未获得新的Telegram独占窗口；本轮没有现场或业务验收。

[精确清理契约](SEPTEMBER_COST_RAW_EXPIRY.md)；[实际结果](evidence/2026-10-11-september-cost-raw-expiry/final.safe.json)；[独立不存在核验](evidence/2026-10-11-september-cost-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删或重跑指令

## 2026-10-09：共享 Gemini 配额 writer 已发布并完成实际包核验

PR257 构建源 `43561cfcf6ab3a8f8af95ee0cba396cac2dbae8c`、merge `10019418ca7bb1118213361c3847c5a80387b64c`。71项新回归、270项定向、2461项全测和三个CI job通过；两环境五入口ARM、实际五函数完整ZIP/共享层/配置保护主检独审以及各300秒稳定完成。实际仅Bot/MemoryWorker共同包更新，唯一非缓存源码为rate_limit.py；564个依赖pyc差异如实保留，其余三函数与层字节不变，PR251身份配置保持。

原writer、RATE key/PT日期、limit和48小时墙钟TTL不换。强读区分整行缺席与存在坏行；已有计数仅接受有限非负整数，写前拒绝坏值。合法行CAS设置精确next，至多三轮只重试明确RetryAttempts为真整数0的条件冲突；不明写不自动重写/退款。合法耗尽仍递增，原ClientError不可用结果与非ClientError/logger异常传播保持。没有观察到线上坏行或超额，不能把源码缺陷称为已发生线上事故，也不声称跨业务重送严格一次。

新实际包28例本地禁网ARM合成及独立直接原流/6模块/完整包/容器移除核验通过，存储和提供方为本地seam；没有新Telegram、模型、线上故障或自然样本测试。104文件费用闭包仅writer变化、原五Memory计费owner保持，新时点reader通过7次只读核验，非持续模型许可或实付。原final中的probe/budget pending是阶段记录，由后续真实回执闭合，不改冻结报告。

首次canonical本地KeyError发生在云上传前；静态控制流与保全输出将其定位到dev不含两个prod-only旧规则，原运行traceback未直接捕获，不能冒称直接异常栈证据；原dev15,263文件和原工具/失败回执保全。新V2只接受dev精确缺席、保留prod原约束，随后完成原dev首次ARM与prod首次构建/ARM；不冒称首次成功。执行前留证工具缺口和本地fixture失败均保留。发布包含真实云读取/资产准备和每环境单次Execute，不能将本地探针0云扩大为整轮0云；CI既有OIDC/CDK只读另计。

新增原文责任为Oct16 18:48:47.827167UTC，精确原文/含原文派生按本批release-raw-retention.safe.json；安全聚合/hash及完整ZIP保留。原十项期限不变，Oct13/14各两时点分开。Z01/Z10/Z12–Z17及Epic原状态保持，20工单14OPEN/6CLOSED，自然0/50有据、0/20未知、production_ready=false。Y相册旧绑定已失效，需新reader/工具绑定独审和新的Telegram独占窗口后另执行；本次不发送媒体。

[实际发布证据](evidence/2026-10-09-shared-quota-writer/release.safe.json)；[有限修复合同](SHARED_QUOTA_WRITER_REPAIR.md)；[精确保留台账](RETAINED_COPIES.md)。

## 以下为此前已冻结阶段，不作当前入口或重跑指令

## 2026-10-09：答案重送原文清理准备与共享计数器有限研究

Oct12答案重送批次原文已完成新的精确清理准备：原ledger全部247项仍在且hash一致，其中246个private JSON及含原文的click-intent.safe.json；217保留文件、18目录完整。新工具正确性/维护PRE、唯一只读inspect和独立本地复核通过，零删除/云/UI。原期限2026-10-12 17:15:22.532382UTC不变；到期公告、全量身份/字节/时点门禁、唯一apply和独立不存在仍待。文件移除不是安全擦盘，不能把准备当责任履行。

独立源码研究还确认共享Gemini计数writer的两个具体缺口：已存在但缺计数字段的行会静默起算；有限小数写后经int转换可能返回合法正整数。PR248修复的是消费端结果门禁，不含这些writer缺口。没有读取实际云行，未证明线上存在坏行或越额；健康整数的原子增量也不能据此称并发故障。下一修复须沿原RATE owner，明确强读/条件写、有限冲突与SDK已重试的不明写边界，再独审实施；本轮仅研究，未修改产品代码或形成操作PRE。

相册批次仍等待用户确认约15分钟稳定Telegram窗口，未发送或执行新云preflight；旧STOP与N/A/M/R证据不变。Oct11九文件清理准备已完成，Oct8九日志责任已履行，不重复原工具。十项原文/副本期限均保持，无新增原文期限。运行仍PR248字节/PR251配置，当前G reader不变；没有本轮模型/预算读取、运行发布、付款或自然样本，CI既有OIDC/CDK只读预览另计。20工单14OPEN/6CLOSED、EpicOPEN，自然0/50有据、0/20未知、production_ready=false。

[本批清理契约](QUIZ_ANSWER_RAW_EXPIRY.md)；[准备证据](evidence/2026-10-12-quiz-answer-raw-expiry/preparation.safe.json)；[独立准备核验](evidence/2026-10-12-quiz-answer-raw-expiry/independent.safe.json)；[共享计数器研究](SHARED_QUOTA_WRITER_RESEARCH.md)；[副本台账](RETAINED_COPIES.md)。

## 以下为历史阶段，不作当前重跑指令

## 2026-10-09：相册工具准备完成，等待稳定现场；Oct11清理已预检

Z01相册有限计划、两张固定合成图片及五个新工具已完成正确性和维护PRE，43项主离线控制、34项独立离线控制通过。目标仍为专用dev群的一次两图相册与一次明确Reply ask；先验证两张真实输入与360秒有限静默，再核完整两图应用调用链和答案语义。正式测试群上下文建立前，Telegram在主操作者未操作时改变账号/会话，原因UNKNOWN；已询问约15分钟独占窗口，尚待回复。本批未执行云preflight、预算reader、上传、发送或模型测试；没有新增原文期限，准备通过不等于业务通过。旧批次UI_STOP及N/A/M/R完成证据不变，不续发旧草稿。

独立工作已推进Oct11九月费用原文到期准备。按两份原ledger与历史独审hash，核准九个实际文件：六份AWS响应、两份Google CSV和一份主UI观察；57份列明保留文件、6个目录及37个未创建预留槽已核。新工具PRE与只读inspect完成，独立再核九文件仍在、保留项hash不变，零删除、零云API；原期限仍2026-10-11 17:01:48.147210UTC。到期前不得apply试探；到期当轮新公告、现场hash/身份/时点门禁、唯一apply后独立不存在核验，才能记履行。原v1公告时效和日志失败边界已修并保留旧报告，不冒称首次无问题。

运行字节仍PR248，身份配置仍PR251；文档提交不发布Lambda。当前十项原文/副本责任与精确期限不变，Oct8九日志原文已清理不重删。本次没有运行发布、控制/预算写入、付款变化或自然样本；后续CI既有OIDC基础设施只读预览另计。Z01/Z10/Epic仍OPEN，20工单14OPEN/6CLOSED，自然0/50有据、0/20未知、production_ready=false。

[相册有限计划](Z01_MEDIA_ALBUM_ACCEPTANCE.md)；[媒体准备证据](evidence/2026-10-09-z01-media-album/preparation.safe.json)；[清理精确范围](SEPTEMBER_COST_RAW_EXPIRY.md)；[清理准备证据](evidence/2026-10-11-september-cost-raw-expiry/preparation.safe.json)；[独立准备复核](evidence/2026-10-11-september-cost-raw-expiry/independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为历史交付阶段，不作当前重跑指令

## 2026-10-08晚：九份CloudWatch临时原文已到期清理

原七日期限仍为2026-10-08 17:13:39.091570UTC。实际九个精确文件已逐个移除，首次完成于2026-10-08T17:13:39.209172+00:00，最后完成于2026-10-08T17:13:39.211508+00:00，分别比原期限晚0.117602秒和0.119938秒；没有提前删除或变更期限。每个unlink的意图/结果时间保留，唯一apply完成后独立重新核九份不存在、41份列明同目录保留文件hash不变，公告/工具/原ledger/报告和18条顺序journal一致。

范围仅原采集八份API响应与selected.private.json，共九个原文文件，没有raw-006目标，没有新增原文或派生副本。原ledger、安全聚合、真实普通topic FAIL、19项未分类结果及旧工具失败报告均保留。文件移除不是安全擦盘或所有历史CloudWatch/外部副本已消失；本次没有云API、Telegram、模型、运行发布或控制/账本变更，也不是全包/跨资源事务验收。后续CI的既有基础设施只读预览另计。

十一项编号责任中的Oct8这一项已履行，剩余十项原期限和身份不变，最近为Oct11 17:01:48.147210UTC九月费用九份原文；Oct13和Oct14各两个时点保持分开。用户导出、现役PITR及业务恢复数据保留，原37个在线退役对象计数不变。Z10/Epic仍OPEN，20工单14OPEN/6CLOSED；其他业务/费用及自然试用继续，自然0/50有据、0/20未知、production_ready=false。

[精确清理范围](CLOUDWATCH_RAW_EXPIRY.md)；[实际安全结果](evidence/2026-10-08-cloudwatch-expiry/final.safe.json)；[独立不存在核验](evidence/2026-10-08-cloudwatch-expiry/independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下保留此前阶段，不作当前待删或重跑指令

## 2026-10-08：修复后新提及与原生 Reply 有限通过

PR251 身份配置修复后，本批仅发送两条新公开输入。提及2413得到完整正确答案2414（41）；原生Reply2415明确指向本批新答案2414，得到完整正确答案2416（56）。两条输入均一次提交，各自持久请求SENT、严格一条SENT回答及精确反向关联、lease已释放。两条真实Lambda请求都有完整START/END/REPORT与凭据验证、入口update_id及精确消息授权桥接；48条应用JSON属于这两个完整请求帧。每个固定窗口的Filter/Get分页事件多重集合一致。独立17次只读确认六条请求/租约/回答记录逐值不变，dev五函数配置、三表身份与CONTROL保持；它是顺序读，不是事务快照或本轮全包/prod重验。

主操作者看到了三条Reply关系，包括发送后点击R的引用，真实高亮回到13:24的唯一完整M答案；独审直接复核原文及主UI观察，没有独立操作UI。原生数字ID和链接未取得，以上ID来自唯一输入hash/actor/来源及持久关联，不能称UI提取。两个答案都为中文，输入为俄文；本批原契约核数学语义与完整短句，语言观察如实保留，不扩称多语言或多轮上下文验收。

主工具61读、独立17读、当前G预算reader新label7读，合计85次操作者AWS读取、零直接云写；真实Telegram输入及模型/业务持久操作另有实际发生。共享PT日Gemini计数由缺席到6，不把全部6归这两题、当供应商完整请求数或实付。时点预算PASS不是模型许可。没有新部署、配置修改、故障注入或支付变更；运行构建仍PR248，实际身份配置仍PR251，当前reader仍G。

本批工具PRE先发现JSON转义内容漏检，修复后24根离线控制、31独立控制通过；旧NEEDS_REVISION和本地fixture边界、UI记录参数类型误停保留，均发生在业务动作前。它们不是产品场景或线上故障。原N/H的FAIL/UI_STOP与旧题不重跑，本批两次发送和所有已结束采集/核验也冻结。

新增第十一项原文责任：85份实际API/UI原文及登记派生按唯一ledger，于2026-10-15 08:17:52.186798UTC精确人工删除并独审；安全聚合/hash保留。原十项期限保持，最近Oct8 17:13:39.091570UTC九日志文件清理仍待当晚到期执行，不提前。本批是授权账号的业务合成，自然0/50有据、0/20未知、production_ready=false。Z01/Z10/Epic继续OPEN，20任务14OPEN/6CLOSED；频道/媒体及其它业务恢复、实际费用和副本职责仍待，不启用新群或prod记忆。

[本批有限契约](Z01_MENTION_REPLY_ACCEPTANCE.md)；[安全结果](evidence/2026-10-08-z01-mention-reply/result.safe.json)；[独立原始POST](evidence/2026-10-08-z01-mention-reply/independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前阶段与原失败证据，不作当前待做或重跑指令

## 2026-10-08：dev 提及身份配置已修复并完成实际读回

实际公开验收发现 dev 用户名误继承生产值。PR251 已将 development 身份与目标默认值分开，并修正 PR 预览的身份来源；15项新回归、38项infra测试、2390全测及三项CI通过。配置源码 `59674f58cfa7e5f92170b88fa5e0bad5bdf81dff`、合并 `ec72bea66c955782a94b87d10d6d5a7ba1287261`。唯一 development 用户名变量已创建并精确读回；dev 数字ID原本正确，生产身份和其他配置来源保持。

实际配置发布只改 dev Bot 的 AGENT_BOT_USERNAME 为 @zerde_dev_bot；全部两环境五函数及共享层的完整ZIP字节均保持PR248构建源 `8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0`。主检、独立读回和十函数300秒后稳定检查通过；业务资源、控制与预算保护保持，prod没有执行变更集。原五费用owner和104文件闭包不变，新的预算reader已绑定本轮实际配置并通过7次只读时点核验，不是持续模型许可或账单。

一次 ExecuteChangeSet 已获HTTP200；其后堆栈显示更新中、变更集暂为AVAILABLE，原轮询工具因此INCOMPLETE并完整保留。新独审合同只用6次AWS读取确认原次更新完成和精确模板，没有再次部署。独立首次查询默认视图时见三条记录而停止：另外两条是引用原Lambda ARN的动态依赖。新精确合同保全96文件并仅迁移95项ledger路径，直接读回API集成/调用权限符合原模板；随后独立前后同时核默认三行及属性一行，完整配置与包保护保持。此处只证明当前符合原模板及资源身份保持，不声称CloudFormation没有调用依赖服务。dev独立artifact阶段API上限只增加两次属性视图读取到26，原Lambda检查全部保留。首次全测的既有异步DNS超时失败也保留，未改旧测试，后续原用例和完整全测通过。

本次完成的是配置修复；新公开mention/清晰Reply验收仍待另批计划、现场和独审，不能把旧失败输入补成PASS。此前普通文本静默及ask仅有限通过，提及真实FAIL、Reply未发及UI_STOP保持。Z01/Z10/Epic仍OPEN，20工单14OPEN/6CLOSED；自然0/50有据、0/20未知、production_ready=false，不开新群或prod记忆。

当前入口为验收根 `2026-10-08-dev-bot-identity-fix` 的 final-release、最终独审和 budget-DevIdentityFinal20261008A；唯一当前时点reader为该目录 read_budget_published.py，原J reader不得冒充当前配置。新配置证据原文采用第十项期限2026-10-14 21:48:46.021161UTC，第九项公开文本原文仍为同日20:45:55.665021UTC，原八项期限不变。最近到期责任仍为Oct8九份CloudWatch原文，是否已履行以精确清理回执为准；此配置修复没有执行删除。见[配置交付证据](evidence/2026-10-08-dev-bot-identity-fix/release.safe.json)、[有限修复契约](DEV_BOT_IDENTITY_REPAIR.md)和[副本台账](RETAINED_COPIES.md)。

## 以下为此前阶段与原失败证据，不作当前待做或重跑指令

## 2026-10-08：公开文本验收发现 dev 提及身份配置缺陷

本批三条新原生输入中，普通文本在真实接收后的至少360秒有限窗口内保持无自动回复/反应；原`/ask`完整回答正确，持久请求SENT、单条回答关联及lease释放，分别有限通过。提及实际dev bot的输入已认证收到，但三次主读和独立读均无回答请求/lease，完整日志窗没有排队标记：dev运行用户名误为prod用户名，提及入口真实FAIL。数字bot ID属于dev且正确，不把Reply识别推断为同样失败；Reply没有发送。

最后UI变为无选中群的dialogs，原因UNKNOWN，本批永久UI_STOP。原生消息ID/链接未取得；`/ask`采用唯一持久关联与主操作者精确Reply预览，独审复核原文但没有独立操作UI。不得重发本批输入、继续Reply、重跑已结束工具或补猜链接。配置修复另按[有限身份修复](DEV_BOT_IDENTITY_REPAIR.md)执行，尚未部署；运行代码包仍PR248。

主97次AWS读取、独立20次、原预算reader7次合计124次，只计本批操作者读取，不含GitHub研究或CI。实际ask沿原模型链，共享PT日计数4不能全归本题或当账单。128份原文/派生于2026-10-14 20:45:55.665021UTC精确清理并独审；审核脚本曾迟登记和临时0644，已改为0600并纳入原期限，历史偏差保留。原八项期限不变，最近仍为Oct8九日志原文，尚未到期。见[安全结果](evidence/2026-10-08-z01-public-text/result.safe.json)及[副本台账](RETAINED_COPIES.md)。

Z01/Z10/Epic保持OPEN，20工单14OPEN/6CLOSED不变；本批是合成业务验收，自然0/50有据、0/20未知，production_ready=false。不启用新群或prod记忆。

## 以下为此前合同与历史证据，不作重跑指令

## 2026-10-07：Z01现场停止，九份日志原文清理准备

Z01四条新公开文本验收保持 **NOT_RUN_UI_CONTEXT_CHANGED**。有限计划与本地工具已独审；发送前发现输入框草稿和侧栏在主操作者没有操作时发生变化，原因未知，因此本批停止，未发送四条消息，也未写回旧草稿。36项离线工具控制不算业务验收；未执行本批云预检、模型调用或新部署。未来需新批次现场核验，不能移除本批UI_STOP续发。

明天2026-10-08 17:13:39.091570UTC的九份CloudWatch原文清理工具已准备，按原ledger核九份精确文件，保留41份已列同目录文件；到期前不删。原普通topic FAIL、原期限和其余七项责任不改。详见[Z01准备边界](Z01_PUBLIC_TEXT_PREPARATION.md)、[精确清理范围](CLOUDWATCH_RAW_EXPIRY.md)及[副本台账](RETAINED_COPIES.md)。

运行仍PR248构建源`8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0`；本次是准备记录，无产品改动或运行发布。Z01/Z10/Epic保持OPEN，20工单14OPEN/6CLOSED不变；自然0/50有据、0/20未知、production_ready=false，不启用新群/prod记忆。供应商登录缺口不因本轮准备而消失。

## 以下为既有交付和历史阶段记录，不作重跑指令

## 2026-10-06最新交付：显式配额结果门禁已发布

显式Gemini调用现在拒绝不可靠的配额返回：整型计数必须大于0，允许标志必须是真正bool；共享counter故障返回0/True或坏形状不再放行后续模型网络，也不沿该失败换供应商。原writer、合法耗尽与原回退语义、Memory五计费owner均不变。

PR248构建源`8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0`，merge`f42d7dfd03ccb8d7223670a8b852dc0698b656e0`；18新增回归、127定向、2375全测、CI37502789560双job通过。两环境五入口ARM及实际五函数完整ZIP/共享层/配置保护主检和独审通过，300秒窗口后稳定。实际更新Bot/MemoryWorker共同包，唯一非cache源码为gemini_client.py，564依赖pyc差异如实记录；News/Quiz/Operations与层保持。

17例新实际包禁网ARM合成及独立原流/容器清理核验通过；不是新Telegram/线上故障或自然样本。当前104文件费用闭包只改客户端，新reader时点PASS非持久许可。Z01/Z17及Epic保持OPEN；writer底层历史坏行处理和完整供应商账单不在本修复结项范围。 dev首次主读因第三ZIP下载期限而INCOMPLETE，原七文件保全；新独审合同下完整只读续接通过，没有再次部署dev。根三份元数据和独立首STS超时的一个空[]记录共四文件仍按本批最早采集期限Oct13 18:26:43.519150UTC清理；旧ledger路径已迁移，以新精确ledger为准，禁止误删后来成功轮同名文件。 [发布证据](evidence/2026-10-06-explicit-quota-guard/release.safe.json)；[修复契约](EXPLICIT_QUOTA_GUARD.md)。原七项UTC职责保持，新增本轮第八项见[副本台账](RETAINED_COPIES.md)。自然仍0/50有据、0/20未知，production_ready=false，不启用新群/prod记忆。

## 以下为发布前或历史阶段记录（不作当前待做或重跑指令）

## 2026-10-06晚：显式问答准入缺口本地修复，发布待验

Z01公开问答回归准备时，核对PR242发布源码与当前源码发现：原共享Gemini计数器遇DynamoDB ClientError返回`(0, True)`，显式客户端只检查布尔值，可能继续请求模型。该具体路径已本地修复：每次应用尝试要求严格正整数计数和真实bool；无效准入抛出独立异常，终止本次链路，不再尝试Gemini或切备用供应商。共享计数writer、Memory五费用owner、原账本和UNKNOWN责任不改。已经发生的先前模型尝试不由此撤销或重算。

新增18个回归，修复前15失败/3通过，修复后127定向通过；独立正确性和维护审查通过。全测首轮因执行器umask077改变测试预期目录权限而1失败/2374通过，原回执保全，随后标准umask022完整2375测试通过（1个原SDK弃用警告），全部pre-commit通过。CI、两环境实际发布、实际包验收和预算reader重新绑定尚待，不把本地修复写成已上线。Z01/Z17/Epic均保持OPEN，当前运行仍PR242，未发送新Telegram测试或调用模型，自然0/50有据、0/20未知，production_ready=false。

[本轮有限契约](EXPLICIT_QUOTA_GUARD.md)。修复完成后再继续Z01有限真实问答；既有共享writer坏存量字段的转换/补齐、完整备用供应商计费证据另留原工单，不用本修复关闭所有计费问题。七项副本/原文期限沿[原台账](RETAINED_COPIES.md)，不启用新群或prod记忆。

## 2026-10-06：九月账号发票已核对，供应商登录仍待

有限只读查询取得九月一张AWS账号发票摘要：税前USD38.65、税USD6.18、总USD44.83；三种币种投影均为USD同值，不能相加。原始回执独立复核通过。它属于整个账号，不是Zerde独立费用或已付款证明；此前Zerde标签Usage USD1.4977694507仍按CE原口径单列。CE账号Usage比发票税前多USD0.0074992985，原因未核，不臆定为舍入或强行对齐。

Groq和DeepSeek官方控制台均停在登录页，已交用户登录；没有读取账户账单、密钥或修改支付。两项九月消费仍UNKNOWN，不当零。AWS付款/完整历史Free Tier、Google非秘密运行映射/税与付款仍待；Z17和Epic保持OPEN。本轮原工具在端点校验误停，仅1次STS；V2显式正确端点后1次STS＋1次发票摘要成功，共3次AWS只读，原失败保留，独立POST未新增云调用。这不涵盖后续CI的基础设施只读预览。

[本轮范围与下一步](PROVIDER_COST_GAPS.md)；[安全结果](evidence/2026-10-06-provider-cost-gaps/result.safe.json)。新增3份精确发票采集原文于2026-10-13 08:06:04.659429UTC人工清理并独审，原六项期限不变。没有产品代码/部署/Telegram/模型/控制/预算或付款修改；运行仍PR242，自然0/50有据、0/20未知，production_ready=false。

## 2026-10-05晚：答案重送尝试未确认投票，权限已恢复

本轮新公开Quiz发题正常完成，但一次原生点击没有确认投票提交，答案重送验收保持 **PARTIAL_UNCONFIRMED_UI**。临时限制只安装一次、撤销一次；撤销完成于18:04:15.865276UTC，早于固定18:08:03UTC截止，看护在截止后再次确认原策略恢复。最后主读与独立强读均未见该题答案，分数未变；有限日志未观察到poll_answer。答案缺席与空日志都不证明没有请求，也不证明失败、重送或一次计分通过。

[本轮边界与下一步](R3_QUIZ_ANSWER_REDELIVERY.md)；[安全结果](evidence/2026-10-05-quiz-answer-redelivery/result.safe.json)。独立37次只读确认原策略与dev保护保持；不是新运行发布或自然样本。Z16/Epic保持OPEN，运行仍PR242，自然0/50有据、0/20未知，production_ready=false。新增本轮原文精确清理期限2026-10-12 17:15:22.532382UTC，原Oct8/11/17/Nov1/2职责保持。下一步先有限核对Groq九月消费及非秘密归属，不重复本轮已结束操作。

## 2026-10-05：旧stats USER备份七日期限已履行

旧stats的唯一USER恢复备份 `zerde-retirement-stats-20260928` 已删除，主检和独立查询均确认精确备份不存在。删除请求实际始于2026-10-05T08:18:54.216996Z，比原期限晚18.264秒；没有提前删除或延长期限。一次DeleteBackup获HTTP200且原身份一致，独立17次只读确认旧表仍不存在、六张现役表身份/PITR配置投影及两份SYSTEM完整元数据保持。

Z10继续OPEN：CloudWatch九份原文于10月8日17:13:39.091570UTC、九月费用九份原文于10月11日17:01:48.147210UTC精确清理；原PITR于10月17日16:20:38UTC复查；旧memory SYSTEM于11月1日11:46:02.425UTC、旧stats SYSTEM于11月2日08:45:11.254UTC服务到期后精确只读核验。日志/DLQ及其他原台账责任保持；用户导出、现役PITR和业务恢复数据保留。

[本次范围与证据](USER_BACKUP_EXPIRY.md)；[安全聚合](evidence/2026-10-05-user-backup-expiry/final.safe.json)。本次仅该一份备份删除，没有新部署、Telegram/模型/控制/预算/支付操作；运行定位仍PR242构建源`08cc614a2f61d9001f3e2a77b9d9e6a7c73585df`。这是资源元数据读回，不是现役行内容、运行包或自然质量重新验收。自然0/50有据、0/20未知，production_ready=false；不启用新群或prod记忆。此前日期段落保留为历史证据，不作为重复删除/发布指令。

## 2026-10-04：九月费用有限核对已完成，完整实付仍未知

固定UTC九月整月的6次AWS只读查询及独立原始复算确认：Project=ZerdeBot使用费USD1.4977694507（dev0.5206115692、prod0.9771578815），四组CE结果均Estimated=false。标签当前Active，最后更新时间为9月11日，未证明整月覆盖或历史回填；账号Usage38.6574992985及Tax6.18、未标Project池Usage32.5516953201及Tax6.18均不能归给Zerde。不是已付款或完整Free Tier结论。

Google两个已授权账号的九月使用日期报表已下载：dev Zerde Bot的Gemini服务未舍入小计USD0.605498（显示0.61），prod Zerde项目未舍入小计USD0.438845（显示0.44）。Google采用太平洋日期，AWS采用UTC；不直接合成完整实付。账号/筛选关联来自主操作者UI，CSV由独立审阅核算；当前运行key与项目独占关系未另验证。充值、发票调整、税费、Groq/DeepSeek、AWS付款及历史免费额度仍分别未知，Z17保持OPEN。

[九月费用报告与下一步](SEPTEMBER_COST_RECONCILIATION.md)；[AWS安全聚合](evidence/2026-10-04-september-costs/result.safe.json)。本次没有部署、Telegram/模型测试、控制/预算/支付修改或新增启用。运行仍PR242构建源`08cc614a2f61d9001f3e2a77b9d9e6a7c73585df`；自然0/50有据、0/20未知，production_ready=false。费用原文6份AWS回执、2份CSV和1份UI观察于2026-10-11 17:01:48.147210UTC精确清理；原五项职责不变。

## 2026-10-02最新交付：同步日志修复上线，Z02限定结项

日志脱敏与内容最小化按原批准范围完成：原Webhook/formatter/Telegram边界及真实库重试已有证据，CloudWatch发现的topic出口经PR240修复，最后同步Lambda异常正文出口经PR242修复并部署dev/prod；两环境实际包/层/配置主独读回及17例新实包探针通过。

PR242构建源`08cc614a2f61d9001f3e2a77b9d9e6a7c73585df`、merge`fb26b9444ff77b4f797354cea86c0e9c591e2b15`；17新增回归/54定向/2357全测、CI双job、五入口ARM、两环境实际五函数ZIP/层/配置保护主检和独审通过，300秒窗口后配置稳定。实际只更新Bot/MemoryWorker共同包，唯一非缓存源码变化是同步invoker；564个依赖pyc差异如实记录，其余News/Quiz/Operations和共享层逐字保持。新实包17例产生8条安全错误JSON，独立直接原流复核与容器删除/不存在核验通过；没有新Telegram/模型或线上异常测试。首轮实包探针因假AWS凭据synthetic与测试函数名前缀碰撞停在字段断言，stdout空，原INCOMPLETE保全；v2仅修两个假凭据值，17场景和全部期待逐字保持，新执行/独审通过。原内部应用行未留存，碰撞机制来自精确夹具/代码核验，非原流直接观察。dev两更新函数RuntimeVersionArn从9559…变为0aac…，原INCOMPLETE整目录精确保全；只允许本轮精确对象变化、Auto整对象不变，prod实际变化单列于证据。按新窄合同重新完整主读/独读通过；不能从ARN推断平台回滚原因、版本新旧或完整补丁兼容，固定容器也不是托管补丁复刻。prod首次主读首个STS查询ReadTimeoutError的两个原文件保全；新独审入口复用冻结读取实现重新完整只读采集，未重发部署。104文件费用闭包只变同步诊断模块，原五费用owner不变，新reader时点PASS（非持续许可或账单）。

[发布与有限验收证据](evidence/2026-10-02-sync-invoker-log-fix/release.safe.json)；[实现边界](SYNC_LOG_REPAIR.md)。本工单原有限实现与验收范围已完成；历史CloudWatch FAIL永久保留，9份原文2026-10-08 17:13:39.091570UTC精确清理仍归副本台账与自动任务。其它业务恢复、Quiz精确UI链接、费用账单和自然使用由原工单继续，不声称全部历史日志安全。 自然起点仍未建立，0/50有据、0/20未知，production_ready=false；不启用新群或prod记忆。五项到期职责保持[副本台账](RETAINED_COPIES.md)。

## 同日发布前记录（已由上方PR242交付替代）

同步 `LambdaInvoker.invoke` 失败诊断已改为固定消息、函数名和异常类型；原一次 RequestResponse、完整 payload、JSON 解析及异常返回协议保持。新增17个回归，修复前8失败/9通过，修复后54定向、2357全测通过；仍需独审、CI、两环境实际发布和新实包探针后才能交付。

现运行仍为PR240构建源`8708db0387c55f2d38dc2050f584837999d8d775`。Z02保持OPEN，原CloudWatch FAIL保留；本次没有新Telegram/模型动作或新群/prod记忆启用。后续依[同步日志修复契约](SYNC_LOG_REPAIR.md)完成发布，再按原Z02有限契约逐项收口。

## 2026-10-01历史交付：Quiz命令日志修复

PR240已合并并部署dev/prod：/genquiz日志只保留主题长度，完整主题按原payload交付；异步Lambda调用失败仅记录固定字段和异常类型。2340全测、30定向、CI双job、两环境五入口ARM、实际五函数/共享层/配置保护主检独审及新实包本地隔离合成6例均通过。

实际更新Bot/MemoryWorker同包两处源码；另有如实列出的依赖pyc差异，Quiz/News/Operations/共享层实际字节保持。两更新函数同时出现AWS托管RuntimeArn从0aac…变为9559…，Auto策略未改；原dev读回INCOMPLETE整目录保全，新窄合同绑定精确变化后重新完整主检与独审。该现象符合[AWS Auto发布时更新机制](https://docs.aws.amazon.com/lambda/latest/dg/runtimes-update.html)，是行为吻合推断，不声称直接证明平台触发原因或全部补丁兼容性。其它配置保护仍严格一致，固定ARM容器不是AWS补丁复刻。两环境300秒后五函数稳定。104文件预算闭包只变两处诊断文件，五费用owner不变，reader已重绑并时点PASS（不是持续许可或账单）。运行构建源`8708db0387c55f2d38dc2050f584837999d8d775`，merge`43dab2d29be9cbe6eca607939f200b4942958e1d`，workflow ACTIVE。

Z02保持OPEN：同步/quizreconcile使用的LambdaInvoker.invoke仍有任意异常正文诊断风险，尚无本轮线上泄漏实证；下一最小修订已独审。原CloudWatch FAIL和Quiz反馈ID/链接缺口保留；其它业务恢复、真实账单及自然0/50有据、0/20未知仍待，production_ready=false。

[发布与实包证据](evidence/2026-10-01-quiz-command-log-fix/release.safe.json)；[本次边界及下一切片](QUIZ_COMMAND_LOG_REPAIR.md)。本次没有新Telegram/模型调用、预算计量/控制/支付修改或新群/prod记忆启用。CloudWatch原文9文件于2026-10-08 17:13:39.091570UTC精确清理；Z10原四期限仍独立，见[副本台账](RETAINED_COPIES.md)。

## 同日此前发现与本地修复记录（现已由上方PR240发布）

已完成发布包16个Webhook组合与2个真实urllib3重试场景。10月1日对既有dev日志作8次只读完整采集，发现/genquiz自由topic原文进入日志，原结果保留FAIL；两个相关诊断出口已本地修复，2340全测及定向独审通过；这是发布前记录，当时尚未发布。

该阶段Z02保持OPEN：当时实际运行PR235，CI、两环境发布与新出口实包验证仍待；这些发布步骤现已完成，后续同步调用诊断风险见上方最新状态。CloudWatch旧FAIL不被新修复覆盖，Quiz精确UI链接/其它业务/自然门槛不由此完成。

[本轮范围和修复契约](QUIZ_COMMAND_LOG_REPAIR.md)；[原采集安全结果](evidence/2026-10-01-z02-cloudwatch-capture/result.safe.json)。9份原始回执按采集起点＋7天于2026-10-08 17:13:39.091570 UTC精确清理，独立于Z10原四期限。没有新Telegram消息、模型调用、配置/控制/预算或支付变更，不启用新群或prod记忆。

## 2026-10-01：真实urllib3重试日志验收

脱敏与内容最小化已实现并部署；PR232/PR235收紧Quiz调用和提示发送日志。10月1日已完成实际发布包16个Webhook组合场景、69条日志独审；随后INFO/DEBUG两场景真实urllib3默认连接拒绝重试也通过独审，17条JSON日志、8次实际loopback连接拒绝、6条重试警告均符合固定脱敏与隔离契约。

限定剩余：一个既有dev Webhook请求从Lambda入口到CloudWatch的完整采集证据，以及原日志契约逐项对账与独审。Z02仍OPEN。不承诺所有历史日志从未泄漏或穷举全部业务/重试排列；新发现具体旁路另记风险。没有新增启用群或prod记忆。

本轮使用PR235发布时独立下载的完整Bot/共享层，在ARM容器中只连接自身保留的未监听端口。没有Telegram API、AWS或模型调用，没有代码/部署/控制/计量变更；两个容器删除回执及不存在核验齐全。运行源码仍`7d3f42827662cae428bc3276319a165add9c417a`。

[本轮边界与有限下一步](Z02_RETRY_LOG_ACCEPTANCE.md)；[安全聚合](evidence/2026-10-01-z02-urllib3-retry/result.safe.json)。原Quiz反馈PARTIAL、自然0/50有据和0/20未知、production_ready=false及四项副本期限保持。

## 此前同日：Webhook日志组合验收（原范围记录）

2026-10-01使用PR235发布时实际下载的Bot/共享层，在本地禁网ARM环境完成8类输入×INFO/DEBUG共16个组合场景，全部通过且独立复核通过；69条原始JSON日志中未出现测试内容或凭据，路由正证据与零外部IO保护符合契约。 独立逐项复核通过。

本阶段仅证明实际包本地组合；其当时未覆盖项及后续收口界限以上方最新记录为准，不作为全部历史日志/所有业务排列必须重测的要求。 没有产品代码变更、新部署、AWS/Telegram/模型调用或计量改写；运行源码仍PR235的`7d3f42827662cae428bc3276319a165add9c417a`。

[验收范围与下一步](Z02_LOG_BOUNDARY_ACCEPTANCE.md)；[安全证据](evidence/2026-10-01-z02-webhook-log-boundary/result.safe.json)。既有Quiz反馈PARTIAL/精确UI链接缺口、其它业务恢复、自然0/50和0/20及四项副本期限均保持。

## 2026-09-30晚：新版反馈真实补验（PARTIAL）

新版真实提示已在专用dev群出现：请求已保存、后台重试、无需重发；原生Reply点击可跳回本轮命令。同请求在受控准入失败后自动恢复DONE，创建至完成176秒；两个后续观察的题目/poll不变、outbox缺席，恢复cursor继续推进。临时权限限制已提前撤销，截止时间后再核原策略恢复；独立30次只读核验确认同请求完成、原权限/配置/控制保持。

整体仍为PARTIAL：原生消息链接菜单未能打开，feedback消息ID与精确Reply目标链接未取得；不补猜、不降低门槛，不重发本轮命令来补验。daily并发、发送UNKNOWN到DONE、答案先到/GSI迟到及其他失败重投仍待；Z16保持OPEN，production_ready=false。

[本轮脱敏记录](evidence/2026-09-30-quiz-feedback-live/result.safe.json)。这是一次已结束的受控业务合成测试，不能计入自然样本；本轮无代码发布、新群/生产记忆或付款变更。该轮当时运行PR235。

## 此前2026-09-30发布记录：Quiz持久请求反馈

PR235已合并并部署dev/prod：原请求确认保留后提示后台继续尝试且无需重发；处理中、待核对、过期和无效请求分别说明；提示发送或诊断失败不再重试整次出题。实际sendMessage异常日志仅记录类型。原publication/outbox/准入与计分所有者不变。

2334全测、两项CI、两环境五入口ARM及实际五函数/共享层的主检和独审通过，300秒窗口后配置稳定。实际只更新Quiz，其他四函数和层保持；104文件费用闭包逐字不变，预算读取器已重新绑定并时点PASS。运行构建源`7d3f42827662cae428bc3276319a165add9c417a`，merge`6a5acf160092a30b6b718135b11ac4ccb6feb38c`；部署workflow ACTIVE。

新版反馈的真实Telegram补验、daily并发、发送UNKNOWN到DONE、答案先到/GSI迟到及其他失败重投仍未覆盖；不以本地测试或发布成功关闭Z16。其余R3业务/实际费用继续，自然0/50有据、0/20未知，production_ready=false。

[本轮发布证据](evidence/2026-09-30-quiz-feedback/release.safe.json)；[实现契约](QUIZ_FEEDBACK_EXECUTION.md)。此前受控恢复与旧轮次均已结束，本轮没有新发题、模型测试、资源删除或新群/生产记忆启用；副本责任保持[原台账](RETAINED_COPIES.md)。

2026-09-30执行进展：受控Quiz准入失败的同请求自动恢复和有限窗不重复已通过，原产品目标及未覆盖门槛不变。详情见[收尾执行](FINISH_EXECUTION.md)和[证据](evidence/2026-09-30-r3-admission-recovery/result.safe.json)。

## 此前发布记录：2026-09-30 Quiz准入修订

PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。

运行构建源`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，merge`4fda918ab5e5a8f4b65e349c9d6cfb6902d40181`；两环境300秒窗口后的配置重读通过，workflow ACTIVE，新104文件预算reader时点PASS（非持续许可或账单）。[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；[下一验收契约](R3_QUIZ_ADMISSION_RECOVERY.md)。本节记录PR232发布时点；后续受控准入恢复已按顶部证据完成，操作器与该轮请求冻结，不再重跑。后续PR235已修正反馈；daily并发、发送UNKNOWN恢复、GSI迟到和其他失败重投仍待，Z16/Z17及整个项目未完成。

> 2026-09-29 R3增量：9月29日补充：管理员对昨日已完成的原始Quiz执行一次公开原生Reply对账，返回成功。八个精确记录前后与独立强读逐值相同，总分保持1、周分0、两个outbox缺席；UI只新增对账文字，没有新poll。仅通过DONE终态幂等边界，UNKNOWN恢复、故障重投和daily并发仍未覆盖，不增加自然样本。 [验收与下一步](R3_QUIZ_ACCEPTANCE.md)。

> 2026-09-28最终在线退役：[证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)；[执行与边界](LEGACY_STATS_FINAL_EXECUTION.md)；[副本台账](RETAINED_COPIES.md)。旧清理once全部结束，不重跑；运行源仍为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。

> 2026-09-28累计执行更新：PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。 2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。 逐项状态见TASKS/HANDOFF。

# ZerdeBot 可靠性修复与 Memory V2 实施计划

**Intent:** 让机器人可靠地记住成员在本群的明确自述、维护当前事实，并在被明确询问时给出有来源的回答。
**Planning Baseline（2026-09-10）:** 当时正则 profile、长期事实、摘要、向量存在重复知识来源；旧任务及删除生命周期不完整，生产原文保留3650天。现已部署的Memory V2原文配置为30天；截至9月26日仅既有dev测试群启用，prod未启用；旧数据不会因此自动改TTL，清零和真实验收以[LIVE_ACCEPTANCE](LIVE_ACCEPTANCE.md)为准。
**Expected Outcome:** 所有自动社交互动停止；新 epoch 之后的消息成为唯一学习来源；旧记忆在线不可用并按清单清除；业务功能保持可用。
**Target-Perspective Output:** 成员可查看、更正、遗忘或停止记录；同群问答附证据和时间；不知道时明确表达；管理员收到实际故障、恢复和预算通知。
**Truth Owner:** Memory V2 独立 DynamoDB 表及唯一 fact writer。Profile 是有效 facts 的只读投影。抽奖实验已由用户取消，不再保留运行时owner或将其数据迁入新版。
**Contract Boundary:** Telegram source identity/revision -> durable pending work -> structured facts -> live source validation -> explicit answer。
**Cutover:** 停止旧 writer/reader/import/backfill/schedules，隔离旧任务并等待在途执行结束；清单备份和按类型清理；验收后逐群启用新 epoch。
**Displaced Path:** 旧正则 profile 写入、规则失败补事实、旧 memory retrieval/vector fallback、主动插话/reaction/channel comments。
**Value Density:** 保留 Python/Lambda/SQS/DynamoDB；一张新表、一个 fact writer、一条 memory queue/worker、一个 outbox recovery 入口。
**Acceptance Evidence:** 分层多语言 gold evaluation、故障注入、dev 行为验收、真实群至少七天观察及数量/来源/成本/删除证据。
**Evidence Lane:** 本地、构建、部署读回、合成 canary、真实产品样本分别记录，不能相互替代。
**Kill Criteria:** V1 不启用向量，不保留旧知识读写作为 fallback；新版失败回退无长期记忆问答。按2026-09-26用户修订，在启用任何新功能、新群或生产记忆前，先完成旧并行实现和无用资源清理；删除前告知精确清单。
**Architecture Slice:** Telegram/shared logging/explicit ask 接现有 bot；新 memory 域独立；captcha/moderation/votes/news/quiz 独立修复；infra/workflows 统一集成。
**Plan Review Gate:** PRE 已在 2026-09-10 会话独立复查并 ALIGNED；用户明确批准执行。每张实现 PR 仍需 POST/correctness/maintainability review。

## 2026-09-26 执行顺序与同步修订

[收尾契约](FINISH_EXECUTION.md)把执行分为状态同步、退役清理、业务/费用验收、自然试用推广四条线；逐工单状态仍唯一存于task_manifest。每次有实质进展同步计划、证据和GitHub工单。当前仅dev既有测试群学习，原控制/epoch不因同步改变；尚无自然样本。旧残留在线清理闸门已满足，产品质量、业务及副本门槛仍独立检查，本次不新增启用。旧文件中的“验收后删”“Z18只读授权”仅说明当时范围，不覆盖本次明确追加要求。副本期限和Z10责任不被新清理延长。

2026-09-27至28日执行增量：PR223依赖修复、PR224旧源码及PR226本批资源退役均已实际验证；[本轮实际资源退役证据](evidence/2026-09-27-retirement/resource-release.safe.json)。R2声明的在线资源退役已完成，Z10副本仍待，R3业务/实际费用验收继续，不等待空群样本。

## 1. 已批准的产品边界

用户于2026-09-11追加要求：直接在PR #204移除实验性抽奖，之后由用户审阅、批准和合并。本修订取代此前“保留抽奖”及Z19事务修复的产品要求：移除命令、观察、抽奖存储实现与定时恢复；旧抽奖任务无副作用消费。现存抽奖数据可以按显式退役root清单备份/清理，不迁入Memory V2；公共forget仍仅处理记忆记录，不删除共用表。这段是合并前的操作边界。随后用户已合并PR #204，并明确要求继续、允许必要测试；2026-09-11起，本轮具体部署、dev与模型验证及原计划的旧记忆清零已有授权。精确范围、停写、备份和验收条件保持，Z18无关旧资源销毁不因此获得授权。

执行期测量补充（2026-09-11）：Z11 独立故障注入发现，仅测 profile 召回和已输出断言的来源支持，会让“所有已知问题均拒答”绕过原召回目标。验收因此同时要求每语言有依据问题的完整回答召回 `supported_answer_recall >= 90%`；缺答、拒答或未覆盖所需事实均失败。原 profile 准确率/召回、来源100%、未知95%和零容忍门槛保持，gold 标签与接受值不因模型输出而调整。这是测量完整性修复，不代表已有模型达到该门槛。

- 停止普通群聊插话、ambient reactions、频道帖自动评论和 reactions。保留 /ask、直接 @mention、明确回复 bot 的问答及现有业务能力。
- 个人事实只来自本人明确自述；各群独立。身份为 `(chat_id, telegram_user_id)`，昵称是别名，不可按名字合并。
- 同群成员可查询其他成员在本群的非敏感自述，附来源和时间。本人可查看、更正、遗忘、optout/optin。
- 原始聊天保留 30 天，最小事实证据随事实维护；被替代事实历史最多 90 天。职业、城市、当前项目 180 天未确认只能表述为“上次提到”。
- 群规则/共同决定须管理员明确确认；七天话题趋势每日确定性聚合，保留 30 天，不推断性格、关系或成员角色。
- 清零所有旧记忆（历史导入及实时积累），保护其他业务数据；不删除用户本地 Telegram 导出。
- 新增记忆目标每月 USD 100，管理员 Telegram 私聊接收故障/恢复/预算异常，不向群广播。

## 2. 数据及接口契约

### 唯一控制与事实存储

Memory V2 表拥有 learning_enabled、epoch、learning_started_at、subject generation、optout 与删除控制。原先为其他业务语义保留的旧SETTINGS，经完整核验实际只有退役开关且无style，已随本批旧表退役；当前style为单一纯normalizer，不另建无用settings存储。所有 memory 命令使用同一个 V2 控制接口。

SourceEvent 以 chat/message 标识，保存个人 actor id、原始发送时间、Telegram edit 时间、content hash、source revision、逻辑 expires_at。cutover 用原始发送时间；旧 epoch 之前消息及其新 edit 均不学习。更高 source revision 胜出，派生旧 facts 先失效再提取新版。纯转发、sender_chat、bot 输出不生成个人 facts；引用块不归属发言人。安全过滤先于 raw、profile、模型 context 和日志。

Fact 的最小契约：fact id、chat/subject、field/value、证据 source id/revision 与最小片段、observed_at/valid_from、status、fact version、supersedes、last_confirmed_at。只允许 occupation/current_project/location（城市级）/education/tech_stack/interests/communication_preferences。communication_preferences 仅语言、称呼、长度、语气，不能学习指令或未来固定回答。

occupation/current_project/location 是单值更新；tech_stack/interests 等多值仅明确增加或撤销；模糊冲突不自动覆盖。较早来源的迟到提取不能覆盖较新事实。Profile 直接读取有效 facts，不存在独立可写 profile 模型。群规则/决策经同一 writer 写入，权限和确认状态不同。

### 可靠异步边界

一张 V2 表、一条独立 memory SQS queue/DLQ、一个 memory worker、一个每五分钟 outbox recovery。消息与 pending work 同事务保存，提交后 best-effort enqueue；失败由恢复入口补齐。队列只带 `schema_version=2`、epoch、source refs/revisions，禁止原文载荷。

outbox 状态为 PENDING/LEASED/DONE/EXPIRED/FAILED，带 lease、retry/next_attempt 时间。重复 DONE 任务不再请求模型。读取、调用前、提交前检查 source 逻辑到期、revision、epoch 与 optout；facts 与 DONE 同事务提交。预算暂停保留 PENDING，30 天到期明确 EXPIRED 并计未处理覆盖率，TTL 不能代替逻辑到期。

同群最多 20 条、输入最多 8k tokens，batching window 20 秒；worker 120 秒，provider 单次 20 秒、最多两次尝试。SQS visibility 至少 `6 * worker timeout + batching window`。普通学习 p95 <=5 分钟，丢投恢复单列 <=10 分钟。通过 spam review 的正常消息必须恢复安全摄取；pending captcha/spam 隔离期间不学习。

结构化抽取沿用 stable `gemini-3.1-flash-lite`。失败/额度不足保留待处理，不用正则生成替代事实。官方价格需在实现/模型变化时复核，不把供应商宣传当本产品的正确率证据。

### 查询、删除和权限

显式 /ask、mention、reply 开关与 learning 分离。所有查询返回结构化候选并回源验证有效事实，保留精确来源；无可靠信息就表达未知。V1 无 vector query/embedding 路径。短线程不能成为旧记忆旁路。新 ask 同样携带版本/epoch，旧 ask payload 中预组装的旧记忆上下文一律不能执行。

about me/group 确定性展示有效 facts。wrong 强排除指定错误版本；correct 创建有命令证据的新版本。forget this 删除指定 source/fact 及所有派生/历史；forget me 递增主体 generation 并清除旧资料，未来新消息可学习；optout 同时禁止未来学习，只有本人 optin 可恢复。群级命令验证当前管理员身份，普通用户不能修改别人资料。私聊请求需验证来源群 scope，不形成全局 profile。

删除时 STOPPING 阻止新 answer/extraction leases，失效趋势/派生/why 元数据；所有登记的相关回答任务结束或租约到期之后才确认完成。回答生成后、发送前复验实际引用 facts；变化则丢弃并重建。Telegram 发送与数据库无法原子提交，不承诺 exactly-once，也不自动撤回已经发出的历史 bot 消息。普通群删除消息并非 Bot API 保证可观察的事件，不能承诺自动同步所有 Telegram 删除；提供显式 forget。

媒体仅在明确请求时临时分析，metadata/短期线程保持最小必要范围；不自动生成媒体长期个人事实。

### 预算和观测

UTC 自然月：USD 70 模型硬计数上限 + USD 30 新增 AWS 用量预留。抽取、每次重试、携带 V2 facts 的整个问答调用都计入模型预算，避免不可靠的增量 token 分摊。每次请求按价格版本、输入保守上界、最大输出预留；结果不明不直接释放。

预算耗尽停学习和记忆增强；无长期记忆 ask（排除旧记忆答案线程）、确定性 profile、纠错/遗忘继续可用。群趋势不用 LLM。AWS 使用预估量、80% 提醒、90% 停可选新增工作；AWS Budget 不是账号硬止付，原有无记忆功能费用单列。

观测包含接收/拒绝/已处理/待处理/过期数量、学习延迟、来源支持、删除完成状态、模型 token 和预留、AWS 估算与实际可归属费用。通知只发故障、恢复、预算异常，私聊 ADMIN_USER_ID；先验证通知渠道可达。

## 3. 旧数据清零及上线

1. 部署 Z01 guard和Z19退役改动：停止所有旧 reader/writer/import/backfill/schedule；旧 memory/summary/vector/proactive/reaction、legacy ask及抽奖TTL任务全部 no-op。保留 captcha/spam/quiz 等业务任务。
2. 等待旧 invocation 退出，核对队列状态；生成精确 DynamoDB key/vector key 清理 manifest、类型计数和业务保护校验。执行时重新读取，不用审计快照当删除名单。
3. 本地加密备份精确范围数据和向量 key，限七天保留，登记删除日期。禁止把正文/个人标识/secret 放 GitHub、日志或 EVIDENCE。
4. 允许清理 MSG/MEDIA_GROUP/USER/USERNAME/EVENT/USER_FACT/GROUP_FACT/JOKE/DAILY_SUMMARY/TERM/AGENT_REPLY/AMBIENT_REACTION/PROACTIVE/VECTOR_BACKFILL 及确认为记忆的 BOT_COMMITMENT/BOT_CORRECTION。另以 `retired_contests` 明确列出chat/root，校验实际kind、规范key和主体关联，清理该root的CONTEST、CONTEST_RULE及全局CONTEST_TTL_OUTBOX；不靠任意user_id或整CHAT匹配。停旧抽奖writer、recovery rule及旧任务重放核验是该scope前置。保留 SETTINGS、未知族和其他业务表。
5. 独立枚举向量，包括孤儿。专用旧 vector queues 在归属确认后处理；混用 main queue/DLQ 按任务类型处理，禁止 purge。无法立即清除副本时报告最迟 TTL/retention 截止，不提前声明物理清零。
6. 验证旧任务/旧问答不能复活或发言、业务数据 key/count/hash 不变。日志七天、PITR 保留、DLQ 和备份分别登记副本消退证据。恢复旧备份后 memory 默认关闭，禁止自动导回。
7. dev 合成验收后单群设新 epoch/started_at；至少七天且实际样本门槛满足后推广其余白名单群。失败回到无长期记忆 ask，不能重新开启旧 memory。
8. 2026-09-26修订：在任何新功能/新群/生产记忆启用之前删除旧并行 profile/extractor/retrieval 路径和已核实无用的专属资源；先告知清单，先核验3条旧SETTINGS，有有效语义才迁移并保护现役业务。语义检索只能后续独立对照实验立项，不属于 V1。

Z18原工单仅交付清单/手册。2026-09-26用户追加了残留清理要求；具体执行由Z20及[收尾契约](FINISH_EXECUTION.md)负责，先告知[删除前清单](RETIREMENT_INVENTORY.md)，完成依赖和保护核验后操作。不得删除现役stack、共享资源、未核实SSM或整表误伤有效业务。历史在线记忆清零与新资源退役分别记录。

## 4. 执行工单与所有权

详见 [TASKS.md](TASKS.md) 和 `issues/` 中逐任务的范围、契约、替代路径、验证和恢复条件。Epic/issue 是执行镜像；本 PLAN 是跨会话契约来源，EVIDENCE 记录实际状态。

先 Z01-Z04，冻结 Z05 后顺序 Z06-Z11。Z06 还依赖 Z13 的安全审核终态，Z11 还依赖 Z17 的通知与预算观测。Z12-Z16 按独立业务模块可并行；共享 webhook/router/config/infra/workflows 由主代理集成并证明组合行为。每任务独立 PR，冲突时根据契约重放而非覆盖别人改动。不擅自合并 dependabot 或其他无关 PR。

## 5. 验收门槛

- 基线：2026-09-10，HEAD 2f3abe7，593 tests passed；此前 fault injection 证明问题可达，测试全绿不代表可靠。
- >=200 多轮 scenario、>=300 gold facts、>=100 unsupported questions；kk/ru/en/混语分别统计。precision >=95%、明确自述 recall >=90%、个人断言 source support 100%、unknown abstention >=95%。按事实/问题各自分母，不能以场景数冒充分母。
- 错误身份、跨群泄露、敏感泄露、删除复活、业务误删均独立零错误门槛，不能被平均准确率抵消。
- 覆盖引述/转发/否定/变更、同名不同 ID、同 ID 跨群、编辑/乱序/重投、optout、删除重放、混入敏感信息、预算暂停/过期、provider 失败。
- 故障注入验证 captcha 决定竞争、真实 moderation 执行结果、voteban session、news deadline/分群恢复、quiz poll lookup 延迟/发布冲突/答案重放、实际 Lambda 构建和配置。
- dev canary 后单群 >=7 天，>=50 有依据问答 + >=20 未知问题；合成与真实证据单列，样本不足保留 IMPLEMENTED_UNPROVEN，不关闭产品验收工单。
- 自动社交输出为 0；抽奖命令、入口和存储实现移除，旧抽奖队列任务不读写/发言/重新投递。明确问答、captcha、反垃圾、news/quiz 相关回归满足契约。
- 每张实现 PR 做 POST plan/correctness/maintainability review；验证范围与风险匹配。合并、部署、config readback、真实产品效果分别记录。

## 6. 参考方案

借鉴工程机制，不把引入框架当验收：
- [AgentCore actor/session/namespace](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html)
- [Google Memory Bank profiles](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank/profiles)
- [Mem0 custom instructions](https://docs.mem0.ai/open-source/features/custom-instructions)
- [Zep temporal facts](https://help.getzep.com/graph-overview)
- [LangGraph memory concepts](https://docs.langchain.com/oss/python/concepts/memory)
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)

以上方案没有在本产品进行供应商对照实验。V1 明确不迁入 SaaS memory、不引入图数据库或完整 agent 编排框架。

## 执行修订：Z19 移除实验性抽奖

Z19 #178原先负责已确认的抽奖SDK事务问题，历史发现保留在AUDIT/EVIDENCE。用户取消该实验后，Z19改为功能退役，原PR #181不再作为待合入修复。新增改动直接进入PR #204，不再另开实现PR。Z10显式抽奖清理依赖Z19停写/退役证据；Z11保留settings、stats、captcha业务完整性与抽奖输出为零的检查，移除抽奖公平性和真实抽奖验收要求。

2026-09-26字段核验补充：旧prod的3条SETTINGS只有旧memory/agent开关与更新时间，没有style_profile；dev0行，无现役setter。故不为死开关建新settings存储；纯normalizer和V2临时媒体保留。删除前重新验证完整键/字段/类型/整行hash，有新增或变化即停并保护有效语义。此处为9月26日历史核验；随后两次fresh门禁通过，旧设置已随PR226本批旧表退役。详见FINISH_EXECUTION及新资源证据；旧副本责任不因此消失。
