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

## 2026-09-30：真实受控准入失败已自动恢复

一次真实dev公开发题在受控准入失败后保留原GENERATING/outbox；撤销临时限制后，同request/generation自动成为DONE并出现一个真实poll。执行记录创建至完成289秒，后续正常恢复cursor再次推进且题目/poll不变、outbox缺席；主检与独立读回通过。原角色策略、函数配置和Memory控制保持，临时policy已提前撤销并在固定窗口结束后再次确认不存在。

本次仅通过一个受控准入失败恢复及有限窗口不重复，不覆盖daily并发、发送UNKNOWN、GSI迟到、其他失败重投或自然记忆质量。后续PR235已修正已保留请求的反馈；继续原Z16及其他R3业务/费用验收；Z16/Z17保持OPEN，production_ready=false。

[本轮脱敏证据](evidence/2026-09-30-r3-admission-recovery/result.safe.json)。本轮没有新Lambda发布、新群/生产记忆启用或付款变更；该受控恢复验收当时运行构建为PR232的`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，现运行基线以上方PR235记录为准。19项主工具及22项独立工具本地检查只验证操作器，真实结果由本轮原生操作、持久记录和独立云读回证明。

## 此前发布记录：2026-09-30 Quiz准入修订

PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。

运行构建源`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，merge`4fda918ab5e5a8f4b65e349c9d6cfb6902d40181`；两环境300秒窗口后的配置重读通过，workflow ACTIVE，新104文件预算reader时点PASS（非持续许可或账单）。[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；[下一验收契约](R3_QUIZ_ADMISSION_RECOVERY.md)。本节记录PR232发布时点；后续受控恢复结果以上方最新记录为准。

[最终发布链独审](evidence/2026-09-29-quiz-admission/release-chain-independent.safe.json)另行核对原actual回执与新鲜GitHub状态；未重复下载或查询预算，预算时点读仍由原owner单独完成。

## 历史阶段：2026-09-29晚本地Quiz调用准入修订

Quiz调用准入修订已在本地实现并独审：原PT日键强读+条件CAS，坏计数或不明写入不放行，每次Gemini应用重试单独计数，计数故障穿透生成/翻译并沿原GENERATING/outbox恢复；安全attempt/usage未知日志与四语言权限/对账提示同步。完整2306测试通过，尚未合并或发布新包。 CI、实际ARM五handler验包、同一候选dev/prod发布和实际包/保护独审及新预算reader绑定待完成；旧Quiz最长300秒在途窗口单列。真实daily并发、UNKNOWN到DONE、GSI迟到和受控失败恢复仍待验收，不能用本地测试或DONE对账替代。

[执行契约](QUIZ_ADMISSION_EXECUTION.md)；[本地证据](evidence/2026-09-29-quiz-admission/local.safe.json)。 原运行构建仍`01bdc1da2c5d995759eda0dfef99f7b427301d60`；以下既有资源/业务/自然/副本责任不变。

## 2026-09-29：真实管理员DONE终态对账

9月29日补充：管理员对昨日已完成的原始Quiz执行一次公开原生Reply对账，返回成功。八个精确记录前后与独立强读逐值相同，总分保持1、周分0、两个outbox缺席；UI只新增对账文字，没有新poll。仅通过DONE终态幂等边界，UNKNOWN恢复、故障重投和daily并发仍未覆盖，不增加自然样本。 [脱敏结果](evidence/2026-09-29-r3-quiz-reconcile/result.safe.json)。本次八次顺序强读不是事务快照；独审未重复UI动作。新增命令/响应消息ID未从原生UI取得，不伪造。

首次预检比较了不同投影：旧Q记录hash覆盖完整Environment，新工具覆盖Environment.Variables。原INCOMPLETE保留，逐值和独立重算确认无漂移；新预检绑定S4实际发布回执通过。新工具断言曾误用答案status字段，实际owner是state；该断言在保存计划前停止，无云写。运行构建源、原费用责任与控制保持；无新部署/发题/答题/付款。

## 2026-09-28 最后一批旧表/旧参数在线退役

## 2026-09-28晚：真实Quiz正常链路

dev专用群通过原生命令、真实poll和一次实际答题完成正常链路；精确请求的执行、发布记录和poll同代同身份，答案SCORED且总分0→1、周分0，两条精确outbox缺席。执行记录创建至完成2秒；答案记录received/completed同一整秒，不能当端到端延迟精度。

[验收边界](R3_QUIZ_ACCEPTANCE.md)与[脱敏结果](evidence/2026-09-28-r3-quiz-live/result.safe.json)记录本轮证据。前置校验器两次形状误判均保留，不是线上故障。未测试daily并发、UNKNOWN/reconcile、GSI延迟、答案先到或重投幂等；Z16仍OPEN，不增加自然样本。Quiz RPD 0→1只证明该计数变化，不能推导全部SDK/备用供应商调用数或实付费用。


2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。

[实际安全摘要](evidence/2026-09-28-legacy-stats-final/final.safe.json)绑定恢复独审、条件保全、14阶段最终回执、77 API最终独审、精确AV移除及独审。最终读回时间为2026-09-28T08:47:42.132091Z；本批9次云写均有唯一intent/result。原失败/窄续接真实保留，没有重跑已完成的backup/restore。SSM有限审计未穷尽批量读取，不把路径删除当token撤销。

副本独立跟踪：旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。

见[执行边界](LEGACY_STATS_FINAL_EXECUTION.md)和[副本台账](RETAINED_COPIES.md)。本批没有模型调用、Lambda部署、CONTROL或支付变更；Z20限定在线scope完成，Z01/R3/R4及Z10继续。文档PR/CI/合并与GitHub实际状态同步另由本批发布回执记录，不冒充已发生。

## 2026-09-28 六个更早空资源退役

2026-09-28另批两条旧updates队列及四个孤儿日志组已实际删除，六对象不存在和保留七表/十函数保护投影已独立核验；前置失败及窄修复证据保留。原7候选只剩zerde-prod-bot-stats，另有2个旧SSM参数尚待核实。冻结旧表12行与现役精确键对照中，3/4条历史统计已被现役累计覆盖，另1条统计无对应行；8条旧投票没有迁入/过期证据，不能恢复到现役。后续先保护有效统计、明确旧会话退役语义及备份恢复，再另列删除范围；R2/Z20仍OPEN，不启用新功能、新群或prod记忆。

[本批证据](evidence/2026-09-28-orphan-retirement/final.safe.json)绑定原预检失败、最终D、停写/稳定窗、六删除、根及独立读回；未重写原S4/F5–F10报告。没有新备份、CONTROL/预算/模型调用或新运行部署。

# 执行证据

当前入口：[收尾契约](FINISH_EXECUTION.md)、[逐项状态](TASKS.md)、[本轮实际资源退役证据](evidence/2026-09-27-retirement/resource-release.safe.json)、[7候选新只读摘要](evidence/2026-09-27-retirement/earlier-resource-candidates.safe.json)。[最新A/B/C与CE补充](evidence/2026-09-27-retirement/followup-readonly.safe.json)。以下按日期保留历史，不用旧失败或执行前状态冒充当前。

## 2026-09-27：PR226本批28资源物理退役完成，R2整体仍待

PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。

- 五函数ARM构建、逐对象模板/真实changeset、已上传完整ZIP含pyc核验和两环境实际主/独审分别保留；测试计数不代替物理不存在读回。
- prod的Retain脱管与另行物理删除分开，旧表删除前精确SETTINGS与空内容、旧消费者关闭/排空门禁通过。六张现役表和预算inventory/历史/UNKNOWN保持。
- 已保留可选空列表/API singleton规范化、并发设置改变Revision及AWS Auto runtime变化等严格门禁失败和窄续接证据；不把读回适配当业务故障，也不覆盖原失败报告。

本次预算仅在2026-09-27 11:54:48 UTC由原owner只读得到PASS_POINT_IN_TIME_NOT_A_PERMIT；不预留、不改账务、不释放UNKNOWN，也不授权后续调用或代表完整实付。

Z10原PITR复查仍为2026-10-17 16:20:38 UTC；本次删表新增SYSTEM副本已读到的实际服务到期字段为2026-11-01 11:46:02 UTC。这是复查/服务到期信息，不是已物理抹盘证明；日志/DLQ/其他副本职责继续，已移除本地密文/key不重建。

R2更早1张旧stats表、2条旧队列和4个日志组共7候选仍未删除。A/B/C有限只读核验已完成：12行分为4条历史审核统计和8条无法证实过期的投票状态；当前Scheduler/Pipes及所查副本元数据未发现匹配项，外部消费者与历史副本仍未穷尽。须据有效语义/消费者/恢复边界形成下一精确清单；2个旧SSM参数继续保留。R2/Z20仍OPEN，不据S4完成启用新功能、新群或prod记忆。 F5模型与F6/F7/F8/F10受控验收的冻结证据不重跑；自然使用起点仍未建立，0/50有据、0/20未知，production_ready=false。现有dev原控制/epoch保持，prod没有新增CONTROL。

Z03/Z04根据限定scope和实际GitHub关闭记录结项；Z01/Z20/Z10、业务/费用工单和Epic保持OPEN。


## 2026-09-27：更早7候选有限盘点及项目标签费用快照

[聚合补充证据](evidence/2026-09-27-retirement/followup-readonly.safe.json)绑定A/B/C及CE原始报告SHA，不复制私有AV、逐行标识或本地路径。A：12行=4历史审核统计+8无时间/TTL/status的投票状态，不能认定已过期；B：全分页Scheduler/Pipes0；C：账号订阅策略/当前可列导出/精确旧stats独立备份与恢复点0。未证明未知外部消费者或历史副本不存在，7候选及2旧SSM继续保留，Z20不结项。

R2/Z20新增精确私有AttributeValue临时证据副本于2026-10-04 10:35 UTC到期，本批提前完成则提前清理；它不是灾备，也不重建已到期的旧记忆归档。原10月17日PITR复查与本次11月1日SYSTEM副本服务到期分别保留；本次仅登记副本责任；自动任务由根代理按最终入口另行同步。

2026-09-27 10:53 UTC的CE标签归属快照，UTC区间[2026-09-01,2026-09-28)（含当前日不完整用量），UnblendedCost为dev USD0.4216791725、prod USD0.8473312256，合计USD1.2690103981，Estimated。未标Project的Usage USD25.9433726729和Tax USD4.86不分配给Zerde；不是实付、模型账单或完整Free Tier核算，不与Memory预算估算/UNKNOWN预留相加，Z17仍OPEN。 本次5次CE（含保全的首轮尝试）、2次STS、0云写；不修改原9月26日费用快照。

## 2026-09-27：PR224旧源码实际发布完成，资源删除未开始

- PR224 source63916a3合并为dd416f86；2264完整测试、18请求逐字等价、CI36271659997两项成功。13个旧算法模块及调用已从源码和两环境实际运行包移除；缓存和包目录形式也核验缺失。
- dev/prod各六函数、共享层、完整配置、映射/规则/写入保护及CONTROL由主检和独审确认；仅三个同源核心包更新。两环境各一次停读前fresh SETTINGS完整核验通过，旧表仍保留dev0/prod3旧控制行。新生产学习未启用。
- 两环境bot构建的依赖缓存字节原有差异，在部署前保全原资产后统一推广dev封存包、重验prod六ARM并核对S3整个ZIP；不把部署后倒推当事前证据。
- dev首次只读报告保存遇到本地变量遮蔽，原INCOMPLETE回执保全，未将其当业务故障；新续跑工具经21项独立离线回归和审阅，新独立reader114离线项通过，再完成两环境最终读回。最终workflow恢复ACTIVE。
- [最终脱敏证据](evidence/2026-09-27-retirement/source-release.safe.json)。S4旧表/vector等物理删除尚未执行；6现役表与预算历史保留，R2整体、R3业务/费用、R4自然试用及Z10副本义务未因本次发布结项。

## 2026-09-10 起点

- 用户批准整个 PLAN；PRE 独立审阅 ALIGNED。
- 审阅基线：main `2f3abe7f9f19d390c2253fc24722af9db521cd17`，593 tests passed；源码与 GitHub main 一致。
- 代码 fault injection 已在规划会话用合成值/内存 mock 验证：captcha 验证后误踢、moderation 虚假成功、日志 token 泄露路径、引用误归属、冲突事实并存、旧 worker 复活、缺源向量进入候选、forget 误匹配 contest。
- AWS 只读审计结果见 AUDIT.md；不是此后部署状态，也不是删除 manifest。
- 尚未上线 Memory V2，尚未删除任何旧数据。所有真实产品验收均待执行。

## 状态规则

分别使用 planned / implementing / PR_OPEN / MERGED / DEPLOYED_READBACK / SYNTHETIC_VERIFIED / REAL_VERIFIED。只允许证据支持的状态。IMPLEMENTED_UNPROVEN 表示有实现但缺所要求的目标视角证据。

每个任务追加：issue/PR、commit、负责范围、验证命令与结果、部署对象与读回、真实样本数量/限制、未完成项、下一步。不得把“返回成功”替代实际消息/持久记录/清理结果证明。

## 工单与计划发布

- 已创建 Epic [#157](https://github.com/Bayashat/zerde-serverless-bot/issues/157) 和 Z01-Z18 [#158-#175](https://github.com/Bayashat/zerde-serverless-bot/issues?q=is%3Aissue+%5BZ)，精确映射见 github_manifest.json。
- 逐工单含范围、依赖、契约、验证与恢复；依赖图无环，18个正文必需章节通过检查。
- 独立 POST/maintainer review ALIGNED：补齐Z06依赖Z13、Z11依赖Z17，以及Z11限定旧实现退役范围。
- pre-commit全项通过；本PR仅计划文档，不改变运行行为，无需重复全量业务测试。
- Z01主代理只读勘察；Z02/Z12隔离worktree实现中，未部署/未生产验收。

## 执行补充：Z19 抽奖事务 SDK 边界

2026-09-10 两次独立 boto3 + Moto 模拟确认，Resource client 与手工 TypeSerializer 叠加导致抽奖事务双序列化并取消。先前抽奖生命周期的设计可借鉴，但实现的 SDK 层必须修复；原 MagicMock 绿测不足以证明该路径可运行。新增 https://github.com/Bayashat/zerde-serverless-bot/issues/178 独立修复，Z11 的业务保留验收依赖它。未调用 AWS 进行真实写入。

## 第一批源代码交付（2026-09-10；无部署）

| 工单 | PR / commit | 本地完整测试 | 独立审查 |
|---|---|---|---|
| Z01 | #180 / ccc49e2 | 609 passed | ALIGNED，269重点；补断spam旧MSG与wrong旧事实入口 |
| Z02 | #177 / 63f15ea（继5b2a900） | 631 passed | ALIGNED，85初审+32最终兼容回归 |
| Z12 | #179 / 7592ad3 | 626 passed | ALIGNED，83重点；补旧答案不能影响新join |
| Z19 | #181 / 0c1c833 | 597 passed | ALIGNED，21重点，实际SDK+Moto事务 |

以上为各自基于2f3abe7的独立分支，测试数量不能相加当作集成证据。尚未合并、部署或验证真实Telegram效果。Z12上线需同批Z13修复SPAM_CHECK的captcha读故障调用方。Z01上线需Bot+indexer同修订、停旧客户端/schedule并排空旧实例。Z03/Z04仍在实现/复审；Z05只开展独立契约，不提前启用学习。

GitHub #176的两个CI检查通过，但reviewDecision=REVIEW_REQUIRED；平台审阅门槛尚未满足，不将其描述为已合并。

依赖补充：GitHub Dependabot当前uv.lock有24个open advisories（18high、5medium、1low），涉及Pillow/urllib3/idna/pyasn1/cryptography/CDK。Z04按官方advisory修复版本做定向升级与真实ARM包导入回归；不能只把带漏洞的旧依赖锁成可复现。

## 第二批与本地集成证据（2026-09-10；无部署）

- Z03 #182 / 2489044：删除白名单与向量清理outbox，615 full（最终TTL0/invalid补充2项后仅重点复验，未将其虚报为新full）；root269重点和独立24 TTL复验。
- Z04 #183 / 321e5c4：599 full，单uv.lock及四个实际ARM64包导入通过；readonly dev diff只是本地默认配置的预览，不能当作生产release manifest。
- Z05 #186 / 0e140a7：645 full，独立52 domain/infra ALIGNED；独立表、事实writer、source+WORK事务，默认STOPPED，尚未接学习入口。
- Z13 #185 / b48cad7：629 full，独立85 ALIGNED；真实SDK事务、发送前ban决定栅栏与CLEAN receipt。临时自动kick安全下限改60秒，固定deadline不延长，防止31秒设置在网络延迟后被Telegram解释成永久ban；Z17同步infra/workflow默认。
- Z18 #184 / 9ea265a：精确资源清理手册，独立ALIGNED；四个日志组再次只读确认0B。无任何删除。

本地 integration 分支 f14bd08 整合 Z01-Z04、Z12、Z19 及计划；首次709/714，通过5项失效mock隔离点修正后 **714 full passed**。保留Z04安全依赖版本并加入Moto，不用旧lock覆盖安全修复。实际CDK synth及禁网Python3.13.15/aarch64四handler导入全通过（bot/indexer/news/quiz），验证测试和真实打包依赖一致。此为本地合并验证，GitHub main未合入，生产未变。

Z06/Z07/Z08/Z17实施中。Z06明确使用短期候选、统一观察版本与跨表CLEAN审批条件；编辑先使旧事实失效。Z08预算API由唯一预算owner实现，抽取与有记忆回答共用，未知调用保守占用，不复用旧fail-open RPD作为成本账本。

## 第三批与摄取/问答接口冻结（2026-09-10；无部署）

- Z17 [#187](https://github.com/Bayashat/zerde-serverless-bot/pull/187) / 9e566ed：624 full；独立42初审+22最终。dev默认按需停用；有效告警及恢复通过独立SNS/operations发送管理员私聊，真实5个ARM64包禁网导入通过。项目成本标签尚未激活，未发送真实通知。
- Z07 [#188](https://github.com/Bayashat/zerde-serverless-bot/pull/188) / 7b7b228：747 full；独立102抽取/趋势/预算，ALIGNED。固定结构化Gemini请求、每次HTTP独立预留费用、拒绝规则生成个人事实。全为合成/模拟provider结果，尚无实际多语言质量分数。
- Z14 [#189](https://github.com/Bayashat/zerde-serverless-bot/pull/189) / bbe4bcc：673 full；独立67投票与执行结果，ALIGNED。generation绑定按钮、临时封禁确认后计数、终态恢复。basic group/缺chat.type及超过365天时长无法保证临时封禁，保守转UNCONFIRMED，不冒险调用；正常阈值和时长不改。
- Z08预算ba1c392 / 75fa928 / 53e344f已被Z07引用：22实际SDK+Moto测试、独立ALIGNED。全项目共享UTC月账本，dev不另获$7。按照模型完整输入上限及额外thinking余量每次先预留$0.458752，有可信实际usage才退差额；缺失/不明计费继续占用。price异常全局暂停跨月保留。此为保守控制额度，不是供应商账单或AWS硬封顶。
- Z06独立复核发现两项P2并完成定向回归：暂停学习不能误清待审批候选；并发已ACCEPTED不能被另一worker反向ACK为EXPIRED。最终96 domain/ingestion独审ALIGNED，主PR发布中；公共Webhook/SQS/worker/infra仍由root集成验证。

Z09统一answer lease接口已冻结：获取、读取当前事实、绑定fact_id/version、发送前强验证、释放；删除先STOPPING阻新租约，等在途结束再确认。Z15分群逐步骤交付与Z16poll/answer恢复实现中。真实群七天试运行、数据清零、AWS资源清理、部署和合并门槛尚未执行；不能把上述PR状态当作上线或产品验收。

## 第四批与实际后台入口（2026-09-11；无部署）

- Z06 #190 / 16f2ee9：691 full；独立96。OBS/RAW/WORK准入、CLEAN回执与恢复事务。
- Z09 #191 / b09cc5d：737 full；独立46。统一删除/更正及发送租约。Z08集成复核又补了查询者本人删除栅栏，避免 A 查询 B 时 A 的晚建 receipt 越过 forget；追加修复尚在 Z08 分支。
- Memory V2 runtime #192 / b605cb6：1,045 full；真实6个ARM64资产禁网导入通过。独立worker120秒、740秒队列可见期、5分钟恢复，默认无CONTROL即停止。
- Z15 #193 / 0bef5bb：871 full；独立57。News 固定原始日期/slot/manifest，逐群逐步骤持久状态，UNKNOWN不盲重发，网络DNS与抓取总时限。
- Z16 #194 / 93236dc：870 full 在原实现f558b5b；独立最终79含跨午夜时间修复，不把最后追加用例虚报为新full。Quiz poll发布/强一致lookup/答题与计分outbox；原始scheduled_at错误必须触发Lambda失败。
- 后台公开接线 #197 / 4bef23b：**1,178 full passed**（Python3.13.6，87.76秒）；独立129 focused，scoped hooks通过。fresh dev CDK synth生成6真实产物，在固定ARM64 Lambda Python3.13.15镜像、network=none下导入通过。包括News限定分区IAM、Quiz webhook失败500/持久后投递恢复、每5分钟两类恢复、live-admin own-poll核对及失败DLQ。
- Z10 #195 / 016e2c8：1,072 full；独立61。精确白名单、加密7天备份、代码HEAD/dirty gate、manifest digest、完整旧writer及alias drain、可恢复清理journal。未生成生产manifest、未备份/清理生产数据。AGENT_REPLY/MEDIA_GROUP旧公开路径退出仍为执行前门槛。
- Z11 #196 / dbb553e：1,070 full；独立42。240多轮/516唯一事实/256未知问题；四语言各60场景。只有本地评分器和静态合成gold，标签独立复核PENDING，真实provider NOT_VERIFIED，dev/七天pilot NOT_RUN；完整runtime replay adapter仍需补接。

上表各自分支full不相加。全部PR尚未合并main或部署。feat/zerde-reviewed-foundation与feat/zerde-background-foundation仅固定已审阅依赖，不能当作生产release。Z08正在接显式问答/命令、临时媒体与源删除、群话题、AWS用量仪表和预算监测。模型质量门槛、单群7天样本、管理员真实通知、成本标签激活和生产旧数据清零均未执行。

## 第五批：显式问答、控制、成本与临时媒体（2026-09-11；无部署）

- 群趋势 #198 / 2f2c21a：1,112 full；独立47。七天贡献回源、编辑/删除失效；当前公开显示最多10条经核验来源的技术话题样本，不能表述为全群完整统计。
- 临时媒体 #199 / 06a5599：1,127 full；独立36。一天 metadata-only album 缓存，退出旧 MEDIA_GROUP/AGENT_REPLY；显式媒体不生成长期个人事实。
- SDK计量 #200 / d9fa52f：1,129 full；独立38。实际 botocore wire hook按每次尝试计费上界，未知结果不退款。
- AWS成本监测 #201 / 042623d：1,136 full；独立67。闭合项目资源清单、分块日志/指标/存储估算、原子告警outbox；不是FreeTier/credits分摊或AWS账单硬封顶。
- Z08实际入口 #202 / **9031c16**：**1,407 full passed / 122.83秒**；pre-commit全项、diffcheck通过。fresh dev CDK synth，6个真实产物在固定ARM64 Lambda Python3.13.15禁网环境导入通过。独立core96、cost115，root控制42及模型调用边界/runtime46重点复验通过。
- #202补齐调用者本人/所有引用主体/source版本的发送租约；统一无记忆问答与有记忆问答的消息身份；每次Gemini重试和备用调用前回源。控制命令使用持久回执及原子栅栏，编辑后不误重新学习管理员命令。预算按完整调用预留，无证据不授权可选记忆。
- #202修复计量第一次发生在async/thread时outer context无法清理的问题；实际SDK跨context测试通过。实际成本上界保守包含dev/prod最多10个Memory告警，即使dev当前停用也不少计。成本计费epoch默认0、首次专属资源部署时配置；不同于后来群学习epoch，不能推进它抹去费用历史。
- #202暂停语义：停止模型学习/记忆增强，AWS阈值还停趋势；RAW/OBS准入、待处理恢复和控制继续运行，以保留覆盖与删除能力。这些仍会产生AWS用量，不声称停止全部AWS工作。
- Z10最终跨树独审ALIGNED：原工具61项及原生Moto演练确认17类V2键/独立表受保护；两实际旧task router各14类重放不写回、不发言。切换文档已更新旧实例/alias排空与当前explicit-v2-sources协议；没有生产清理manifest、备份或删除。

这些证据仅证明本地实现和真实打包边界。Logs Insights实际执行、共享用量归因、真实管理员通知、模型质量、Telegram来源链接、dev canary及单群七天仍待验证。旧实现暂留隔离状态，按Z11验收后才退役，不提前恢复任何旧记忆读取。

## 首次完整组合与交接（2026-09-11；退役抽奖前的历史快照）

- 完整代码 [PR #204](https://github.com/Bayashat/zerde-serverless-bot/pull/204)，源码提交 **c2bed1b**。该提交已组合全部独立修复、公共入口、清零工具和最终评估工具。后续计划/证据归档为文档变更。
- **1,620 tests passed / 150.64秒**，Python3.13.6；all-files pre-commit和diffcheck通过。集成前1,539/127.03秒也通过，该阶段证据以1,620为准，不累加各分支测试。
- fresh dev CDK synth与6真实Lambda资产ARM64/Python3.13.15禁网导入通过。此后只加入dev评估工具/语料/文档，不改变Lambda源码、资产或锁文件。共享入口独审191项ALIGNED，保留Memory与News/Quiz的所有路由、依赖注入、HTTP500、IAM和恢复调度。
- 最终评估 [PR #203](https://github.com/Bayashat/zerde-serverless-bot/pull/203) / 7be7370（作者分支1,488 full）。独审81项、3个原生Moto故障注入和18场景/36检查点/16种事件的独立CLI回放通过工程检查。修复管理员确认类型、同一检查点前写入又删除的敏感RAW漏报、全部known问题拒答仍假PASS三项P2。
- 集成分支再次独立CLI执行 **240场景/404检查点/16类事件**，无缺fixture、无网络调用；813个WORK为797DONE、4PENDING、4PAUSED、8EXPIRED。没有把暂停或过期算完成。执行源码指纹 `ee65efe71a61600ed0a87b5caf63a40ee2110789728bd8a7670816c1c703b662`，覆盖129个指定源码/锁文件；不是已安装依赖或生产镜像认证。
- [固定provider报告](evidence/2026-09-11-fixed-provider/report.md)与provenance已归档。**数值FAIL、模型NOT_VERIFIED、观测不完整**：profile precision95.83%/recall21.07%，来源250/260，未知244/256，known完整回答21/224，缺16个答案。fixture刻意有限，并非Gemini；不能据此声称真实模型达标或不达标。六项零容忍在这批合成输入均0，不代表生产证明；所有延迟来自合成时钟。raw观测约4.66MB保留在本地 `/tmp/zerde-complete-evaluation/observations.jsonl`，仓库保留报告、provenance、命令/摘要与完整可重现语料。
- GitHub只读快照：main仍为2f3abe7；#204 OPEN、REVIEW_REQUIRED、BLOCKED，未绕过审阅门槛。全部工单保持代码/部署/真实验收分离；Z11和#134来源链接不因测试通过关闭。
- 最终dev只读diff：CDK CLI2.1119.0，`cdk diff -c env=dev --no-change-set --method=template` exit0，1个stack有差异；直接模板比较/lookup role，不创建change set。33新增、29修改、14删除，删除全是旧dev告警；新增operations/worker、V2表、4队列、SNS、恢复规则/映射/IAM，既有4Lambda更新。默认dev预览6Lambda并发0、3mapping false、3rules DISABLED、0alarms、4表PITR关闭；共享Layer替换仅模板推断。管理员未配置、计量epoch0，**这是本地默认配置与已部署dev的差异，不是生产release manifest，不能原样部署**。私有原始日志 `/tmp/zerde-final-readonly-dev-diff.log` 权限0600；没有云写或生产diff。

继续执行以 [HANDOFF](HANDOFF.md) 为入口。未执行合并、部署、真实模型调用、Telegram发信、成本标签激活、生产manifest/备份/清零、旧AWS资源删除、dev canary或七天群试运行。当前已批准的Z18交付仍仅清理手册。生产物理副本清除和验收后旧实现退役仍是明确未完成项。

## 用户修订：抽奖退役（2026-09-11；PR #204）

用户要求直接在现有PR移除实验性抽奖，之后由用户审阅、批准和合并。退役源码提交 **158cfe729d0670461b739471b5c976709c2aeca2**，随后打包缓存修复提交 **da6d77d4334c1eb70287ffe86c3270e416a6e303**；后续为计划/证据归档。此节取代上节的最终源码与测试数量；上节仅是退役前历史快照。

- 删除三个contest模块、命令注册、webhook观察、依赖注入、队列生产方法及prod专用恢复规则。运行源码只剩两种退休任务名，统一在`memory_cutover.RETIRED_TASK_TYPES`声明；main/vector路由均在chat解析和任何业务依赖前丢弃旧任务。16个双路由/双类型/异常chat案例与混合批次证明不读库、不发信、不再投递，正常业务任务仍处理。
- 清零工具新增显式`retired_contests`群/root清单；原默认范围不扩大。四种历史记录分别校验规范key/kind/身份，独立处理缺META的孤儿alias/outbox，加密备份及manifest包含所选数据，outbox最后删除。每批确认旧writer/任务/recovery已停，已删除规则仅接受明确NotFound读回；共享表和队列保持。
- 独立cleanup审阅 **ALIGNED**：原69项加临时3项原生SDK/Moto故障实验，共72 passed。实际旧repository生成两root后仅删除选中root；35参与者跨批期间规则重新ENABLED立即停止；备份后新增属性中止且零删除。完整库存、停写和change freeze仍须真实执行时提供，模拟不替代生产证据。
- Memory评估改用实际SETTINGS、CHAT_STATS、CAPTCHA_PENDING行及其真实表键；九种删行/改值/加字段故障须报业务损坏。语言gold、问题和provider响应字节未改，基线hash见[不变项证明](evidence/2026-09-11-contest-retirement/unchanged-language-baseline.json)。移除抽奖公平性和真实抽奖验收要求，未降低记忆质量与其他业务保护门槛。领域/评分器独立复核 **ALIGNED**；root重点90 passed，运行入口重点86 passed。
- 退役源码先通过 **1,609 tests / 172.15秒**；增加打包缓存检查后，最终`da6d77d`再次全量通过 **1,621 tests / 182.88秒**，Python3.13.6。all-files pre-commit及diffcheck通过。数量变化包含删除旧功能专属测试和新增退役/数据边界测试，不能与各分支数字相加。当前无可执行抽奖源码和陈旧文档路径引用；旧缺陷仅作为历史审阅证据保留。
- 本地CDK模板与90d19b5比较：[差异记录](evidence/2026-09-11-contest-retirement/local-template-retirement-diff.json)。dev资源定义不变；prod仅少一个抽奖EventBridge规则及共享队列policy中相应投递授权。此比较使用测试construct占位资产，说明基础设施定义范围，不能替代真实产物或已部署AWS读回。
- 实际打包发现旧源码删除后，本地ignored `__pycache__`仍会被PythonFunction复制。`da6d77d`通过唯一共用BundlingOptions给六Lambda排除本地缓存，shared Layer使用明确glob；资产probe拒绝自有缓存或退役contest模块，允许pip依赖编译输出。39项专项测试通过，包括真实CDK Layer AssetStaging哨兵过滤、六入口接线与probe拒绝回归；root独立复核 **ALIGNED**。没有依靠手工清空工作树来掩盖打包残留。
- `da6d77d`在无.env隔离树重新实际dev synth **exit0**；故意保留21个源缓存哨兵时，六Lambda及Layer均未复制这些输入，contest文件为0。六真实入口在固定digest ARM64 Lambda镜像、Python3.13.15、禁网条件下全部import通过，模板保留四表和八队列。host为Python3.13.6，与容器运行时区分；[实际产物证据](evidence/2026-09-11-contest-retirement/actual-bundle-verification.json)含源码SHA、资产ID及探针结果。没有部署或云写。
- 在当前领域代码执行240场景/404检查点/16类事件固定provider回放，无缺fixture、无网络；813个WORK=797DONE/4PENDING/4PAUSED/8EXPIRED。执行范围126个源码/锁文件，指纹`d2c1756b706dbc6e0077fe1eb44a349e9ae58c9731eadf7fab38d971fb5979b4`。新[报告](evidence/2026-09-11-contest-retirement/report.md)、provenance及[重现记录](evidence/2026-09-11-contest-retirement/run.json)已归档；旧报告保留为历史。数值仍如实 **FAIL**：recall21.07%、来源250/260、known完整回答21/224；真实模型仍 **NOT_VERIFIED**。退役改动未通过改gold或换假provider提高分数。

没有合并、部署、AWS/Telegram写入或实际清理。线上现有抽奖记录不因此消失，不迁入Memory V2；后续须按明确清单、备份、停写证据执行。仍保留Z10生产清零、Z11真实模型/dev/七天单群和Z18云资源清理等未完成状态。用户审阅入口仍是同一个PR #204。


## 合并后发布与真实验收（2026-09-11；仍未完成产品验收）

以上各节为明确日期的历史快照；“尚未合并/部署/清理”等状态已由本节及[LIVE_ACCEPTANCE](LIVE_ACCEPTANCE.md)后续现场记录取代。

- 用户已合并#204，main `f305aae911fffd652b225e6aecd9eded495e2d1a`。生产六份实际运行ZIP和共享层的第一方代码、锁定依赖及配置核验通过，16:22:19 UTC正常业务恢复，四个生产群学习均STOPPED。dev真实启停、独立合成DynamoDB18项、18条退休任务回放和私人测试群无记忆问答已验证。实际学习、来源链接和七天单群尚未验收。
- 固定清单为30,794条旧记忆、8,259条向量、3条受保护SETTINGS；精确备份和预检完成，删除进行中。重新全量扫描已确认向量0，表清理及最终业务校验尚未完成。保留副本独立追踪，备份期限不因续跑延长；不把在线删除当物理副本全部清除。
- 真实Gemini完整执行56/240个场景，全部哈萨克语，其余184未完成；[完整56项独立审计](evidence/2026-09-11-real-model-partial/EXECUTED_56_ARCHIVE_AUDIT.zh.md)保持冻结gold和原始分数。观察事实准确率170/170、召回170/173，个人断言来源支持259/267、未知53/60，**仍FAIL**；这些事实计数包括多检查点重复观察。其他语言未经真实模型测试，不能把0/0记为达标。
- 全部8份模型调用账本累计294请求，284已核实用量、10计费未知、0在途。按目录价核实USD0.061156，未知预留USD4.587520，合计责任USD4.648676，单次操作合计USD5剩余USD0.351324；不是实付USD4.65，未知费用没有退款或重置。
- 真实接口、评估及两项质量修复在#207，完整本地1,906项通过，尚未部署或重新真实模型验收。#205修复dev并发/环境容量/旧摘要规则，#206改进固定清单续跑，#208修复标准SQS费用读取；这些都是待审后续PR。
- 账号Project/Environment成本分配标签17:33:55 UTC读回Active。标准SQS真实`InvalidAttributeName`已定位并取得修订reader只读验证，生产费用采集尚未修复。告警与恢复通知已有应用送达证据，旧持续ALARM于17:48:52 UTC单次补发、17:52:44 UTC确认应用发送。完整历史REPORT、账单归属和故障恢复验收仍开放。
- 26个已由#204取代的旧PR已逐head核对并关闭，保留分支；没有重复合并，也没有因此关闭Epic、Z11或其他验收工单。最新执行入口仍为[HANDOFF](HANDOFF.md)。


2026-09-12补充：四个待审后续PR组合已取得[1,951项完整测试及锁/格式检查证据](evidence/2026-09-12-post-merge/integration-check.json)，未重复运行、部署或开启学习。原清理第12轮遇非期限错误后正常停止；新完整status与preflight验证剩余12,993条目标、0向量、原3条业务hash不变，root和独立审阅后继续同manifest。根因仍未知；新窗口不扩大自动重试、删除范围或备份期限。

## 费用采集真实窄窗口通过（2026-09-12 13:49 UTC）

#208当时的窄窗口源码`1040546`修复标准SQS属性及两阶段统计兼容：中间别名隔离、耗时wire字段严格映射，以及逐调用materialize完整性判据（无法求值按违规计数）。最终1,684项完整本地测试通过；源码及真实结果均经独立审阅。

[真实数值证据](evidence/2026-09-12-post-merge/cost-fixed-window-verification.json)：两查询均Complete，32项指标完整，两个worker各3次与指标吻合，prod共享Bot两次V2调用完整；所有返回行invalid_records=0。原失败报告和未知预留全部保留。这个15分钟窗口通过不等于整月覆盖、实付账单、共享非零写入/SQS路径或生产上线效果；没有改生产许可或开启学习。


## 诊断续跑已启动、在线清零尚未验收（2026-09-12 14:29 UTC）

[脱敏执行证据](evidence/2026-09-12-post-merge/cleanup-diagnostic-continuation.json)绑定原清理源码`bb3de235`、同一manifest/scope、两个新副本指纹、root精确批准与实际只读canary。原13:46第4轮停止原因仍未知；原脚本、停止状态和历史报告没有被覆盖，也未扩大未知错误的自动重试范围。

- 新wrapper真实fresh/status/preflight均PASS且无写入；完整快照确认10,956条旧记忆目标、3条原SETTINGS且hash不变、0向量。该数值属于启动前canary，不能当作续跑后的剩余量或在线清零结果。
- 诊断副本166项离线回归 /1.99秒通过；最终启动一致性补丁独立63项 /0.52秒通过并ALIGNED，数量不累加。root批准SHA `a69fcba49fcd2fc530191aa82513c4f5373b3fa7bb5c3fe73cef7574f870da91`已由新controller直接核验消费。
- 14:29:32 UTC启动，14:32:59 UTC读回第1轮APPLYING。固定截止仍是9月13日00:48:32 UTC，未再开12小时；原备份9月18日16:49:52 UTC到期不变。终检和物理副本清除均未验收。
- 14:33:28 UTC自动任务已实际读回ACTIVE、每30分钟跟进；新终检及条件批准已冻结，但终检尚未执行。只有这次新控制器真实成功并退出才允许一次只读终检；完成或异常后恢复每日职责，未知停止不得自动重开删除。

这次清理进展不改变费用15分钟窗口PASS的限制，也不改变真实模型质量FAIL、学习STOPPED及七天单群验收尚未开始的状态。


## 在线清零独立通过，保留副本待处理（2026-09-12 16:20 UTC）

[新的最终证据](evidence/2026-09-12-post-merge/cleanup-independent-final.json)取代前节的运行中状态，不覆盖其历史快照。诊断controller六轮于15:48:31 UTC完成，全部进程/锁退出；16:20:47 UTC单次独立只读终检返回`INDEPENDENT_ONLINE_CLEAN_STOPPED_COPIES_PENDING`，报告SHA `f526229405653d7a42a72c6f4b526ba69b6ec9105cc89506bb3d95345d93fa2c`。

- 实际全表仅原3条SETTINGS且保护hash不变，旧记忆目标0、向量0；四个精确CONTROL键强读缺行，默认epoch及学习STOPPED不变。批准运行版本/环境/写入围栏保持，终检写入0。在线表和空索引资源保留，Z18资源销毁未执行。
- 原归档9月18日16:49:52 UTC到期不变。旧表PITR实读35天，保守上界1789230038加35天所得1792254038（10月17日16:20:38 UTC）仅为复查点，不宣称物理删除。日志/队列/PITR/密文及其他副本仍单列；16:23:16 UTC原每日到期自动任务完整字段已实际读回匹配且ACTIVE。三份归档仍存在，manifest/backup字节未变，journal668字节、独立密钥未删，实际保留metadata与指纹已归档。
- Z10改为`online_clean_copies_pending`，Z19改为`runtime_retired_online_residue_cleared`；工单不关闭，整体验收仍未完成。原未知停止原因与不可变证据保留，后来成功不倒推根因。

费用15分钟PASS、真实模型质量FAIL、后续修复未经真实模型重跑、学习STOPPED、七天单群未开始等边界不变。

清理前18条退休任务回放已通过，但清理后未再次Invoke；本次终检只读，不作为删后不复活回放证据。新epoch前仍须补齐清理后回放，现有到期自动职责不包含该调用。


## 费用修复生产读回与可统计的历史用量完整（2026-09-12 22:25 UTC）

[新发布证据](evidence/2026-09-12-post-merge/cost-monitor-release.json)补充并取代前文“#208待审/未部署”和“仅15分钟费用样本”的当前状态；原f305首次发布、旧窄窗口及清理终检凭据仍完整保留。

- #208合入`7ba14bcb6b73f31ec71077a26d79ce9a99c7593b`，#209于22:20:30 UTC合入main `e0780520dad8f19039b4a640bbf10489fd292210`。发布源码提交为`3bd0567426e050b0ca35db8c7a3bec0dc990a9a5`。本轮1,765项全量测试、all-files hooks、六个ARM包导入探针、两个CI检查与独立审阅通过；不与历史测试数量相加。
- 生产Bot/旧vector入口/Memory worker仅代码更新，第二次真实ZIP读回三包均为`386ba112a2bde866621a30d734caca09ba2cf382d248748e588f4931f1b7bb92`，106份第一方文件及15项依赖匹配。News/Quiz/Operations的f305代码、Layer17、环境、CONTROL缺行与旧写入Deny均保持；没有将#205–#207一并发布。
- 10小时20分钟历史样本通过逐执行配对：worker dev/prod 117/94次、共享Bot dev/prod 5/18次，包含非零共享WRU/SQS。同RequestId重试不再合并成一次费用，窗口外失败不污染明确的当前执行；缺失、重复、歧义及真实错误仍拒绝许可。
- 22:23:29–22:24:34 UTC三次真实canary均HTTP200、无Lambda错误、返回完整费用状态，并强读确认状态匹配、观测时间不早于返回值。前两次健康追赶仍UNVERIFIED，第三次`ESTIMATE_VERIFIED / OBSERVED_GROSS_ESTIMATE`，可统计的历史用量覆盖至1789250700（9月12日22:05 UTC），保守目录价估算1,768,707 microUSD。它覆盖新增Memory AWS的dev/prod预算范围，不是发票、实际支付、Free Tier或未来整月完整费用；未知预留不退，Z17项目账单与费用验收仍开放。
- 22:25:32 UTC读回四个CONTROL缺行、相关告警OK且ActionsEnabled，ALARM/OK动作各1项。未做一小时持续观测，未调用模型、开启学习或更改清理状态。本次短暂暂停的deploy workflow已恢复active、分支保护规则不变；直接代码更新留下CloudFormation旧Code指针，完整CDK部署前须先合入#205并同步当前环境与代码差异。

`ONLINE_CLEAN_COPIES_PENDING`及原归档/PITR到期职责、Z18资源保留、真实模型质量FAIL、#207质量修复未重新实测、学习STOPPED和七天单群尚未开始均保持。不能由费用历史覆盖完整推定产品验收完成。

## 2026-09-15 发布、清零后重放与模型质量发现

#205–#207、#210 已合并，`5669a71` dev/prod 完整部署并读回六实际代码包、共享层、锁定依赖和配置。独立核验队列并发10/3/2、存储身份和CONTROL默认STOPPED；生产旧摘要规则已移除，中文新闻既有手动停用漂移保留。测试群真实显式问答返回验收口令。

清零后两次同步生产调用覆盖18条退休任务，均成功丢弃且没有记忆计量开始；独立前后旧表3SETTINGS原完整哈希一致，记忆0、向量0。备份/PITR等副本的保留期仍单列。完整[发布证据](evidence/2026-09-15-continuation/deployment-5669a71.json)及[独立联合证据](evidence/2026-09-15-continuation/independent-release-and-replay.safe.json)均不代表记忆产品验收完成。

真实模型冻结基线提交155/240场景（152EXECUTED、3UNSUPPORTED），252/404检查点有观测，原gold不变。来源跨度、学历类型、正常偏好误拦及公共fallback观测缺口都保留原失败。独立摘要另存，原report仍是smoke不复用。一次额外限流诊断确认实际dev密钥免费层RPD500已耗尽；该调用单独记账，不纳入质量样本。下一版需新固定源码、新会话完整四语言复验，再做真实Telegram生命周期和七天试运行。

## 2026-09-15 #211合并与新评估启动门禁

[本轮安全证据](evidence/2026-09-15-continuation/public-v25-release.json)：#211按仓库允许的squash方式合入main `5ce82d1bbe09176b8eeecaddbffa95b3afa6a4ef`，审阅head `667e6c9`、唯一父提交`5669a71`及完整树匹配已核实。首个merge-commit请求被仓库拒绝，未合入；随后没有更改仓库合并方式限制。CI `34904175265`两项SUCCESS，完整测试2,179项/397.97秒通过；冻结运行源码`9158201`与最终main仅三份文档及一个测试文件不同。部署workflow恢复；本次dev/prod各六个实际包、共享层、依赖与完整配置读回均通过，独立复核也ALIGNED。三条映射并发10/3/2、21项受保护存储身份、dev一个/prod四个精确CONTROL键强读缺行均核验，旧Deny及生产中文新闻停用状态保持。这里的上线结论来自本轮实际产物，不能推导真实模型质量通过。

新public-v1/self-claims-v2.5评估尚未运行，240固定场景、冻结gold和完整分母保持。十个旧账本816次尝试合计费用责任USD18.977963，其中明确用量标准价USD0.169131、未知预留USD18.808832；新会话限额USD81.022037，累计USD100。这些是责任管理与标准价核算，不是实付发票。旧155场景提交和85未提交记录保留，免费日配额500耗尽后等待恢复，429即暂停。

私有启动器修复resume丢账本时可能重建空费用账本的问题：在SSM之前、启动子进程之前均以只读方式核验原SQLite文件/结构/会话指纹，不调用创建构造器修复。缺失、空、symlink、错误schema/config及非法计费标量都拒绝；合法初始化空账本或INFLIGHT不被误拒绝，原预留不退款。作者28项临时SQLite回归/0.21秒、独立同28项/0.23秒通过，数量不相加。实际check为0 SDK/模型调用，旧十账本SHA前后相同，冻结源码clean。这个门禁不承诺防御最后校验后恶意并发替换本地文件，也不证明模型质量或配额可用。

同一`zerde`自动任务兼顾后续验收与原备份期限；每天12:49:52/21:49:52 Almaty两时点，9月18日21:49:52精确到期范围不变，不能因验收暂停延长归档期限或因备份完成取消未完成验收。在线清零、清零后回放已完成，不重新删除；学习STOPPED、真实生命周期及七天样本门槛仍单独保留。

## 2026-09-18 F1 发布补录与 F2 离线测量

F1 PR#213/main f6c18b9 已完成两环境部署和独立实际包、配置、存储身份读回；完整安全摘要及原读回指纹保存在[发布摘要](evidence/2026-09-18-f2/f1-release-summary.safe.json)。该记录对应9月17日发布窗口，非本次重新调用AWS。

F2 新增 semantic_review 独立测量owner，未改旧gold/scorer、预测、账本或生产路径。PRE及最终correctness/maintainability均ALIGNED；首审4个工程缺口均以故障测试闭环。81项专项通过；整仓2301项在lint前同语义源码通过，最终lint后81项与hooks通过，CI待本PR提交后独立全套。精确源码/测试/契约指纹及限制见[验证回执](evidence/2026-09-18-f2/verification.json)。测试不证明新版真实模型质量。

旧public-v25清单只读核验112 expected/108 actual学历项及480全文项，所有语言和033缺答保持分母；原run与账本字节不变。无新模型调用、无学习启用、无备份删除。新运行还须首次调用前登记policy与独立审阅者；真实Telegram闭环及至少七天试点仍待执行。

## 2026-09-19 F3 完整复核及本地备份移除

F2 PR #214 已合并，F3 240 场景已记录、480 全文已独审；仍有 1 个未完整执行检查点和 3 段无依据状态/能力表述，整体 INCOMPLETE。原 strict 结果、gold、输出及账本冻结不改。完整数字、费用与证据见 [F3 结果](F3_RESULTS_2026_09_19.md)。

F4 [执行契约](SOURCE_RETRY_EXECUTION.md)已 PRE ALIGNED，代码和针对性回归已实现，POST/correctness/维护性均 ALIGNED，完整 2331 项测试和 hooks 通过；CI及合并发布待执行，尚未新模型复验。继续独审/CI/精确交付，不能开启学习或重复已完成的 F1/F2 发布。累计模型费用责任 USD 19.838358，剩余 USD 80.161642，非实付。

本地 3 个归档及专用密钥已删除且独立核验，实际比期限晚约 5 小时，详见 F3 结果；不重复删除。PITR 10 月 17 日复查及其他副本职责保留。Telegram 记忆生命周期和七天真实单群试点仍待完整质量门槛通过。以下旧时间段仅保留历史，不作为当前待执行状态。

## 2026-09-22 费用监控分块交接修复（上线待验）

F7发布与真实客户端清理已经完成；本次新检查发现原成本监控每次只推进一个12小时块，
在半天交接时正常成功也可能先补旧块、留下新块，造成约一小时的许可缺口。
现场保留的13:08与14:08查询窗、Complete结果和DAY覆盖，加上原owner连续时钟离线复现支持该原因；
原13:08预算reason已被后续观察覆盖，不能把推断当作历史行直接读回。18:03UTC现场已由定时任务自行恢复，未手动改账本。
独立诊断摘要SHA256：`50452b04308f4c94fa62b1be013a2a84d573b12008e44dcaaccea77d23037fa1`。

修复仅调整原owner的有界调度，每次最多补两个块，所有原计量与预算围栏保持。
验证范围包括正午/午夜交接、第二块失败后的恢复、较大历史积压、未知扫描责任和普通单块刷新。
代码验证、部署与两真实Telegram账号验收分别记录；本段不是上线或自然七天试用完成声明。


2026-09-23 #219：确定的个人事实/来源归属拒绝使用明确的四语言提示，并由原CommandReceipt记录DENIED终态，重投不执行业务。保留原scope/lease/CAS、未知写入恢复及来源purge恢复检查。新增28测试、相关82组合通过；独立正确性与维护POST ALIGNED。首轮missing-source测试仅mock原repo而非实际scopedrepo的夹具问题已修并独立复验。见[执行契约](COMMAND_DENIAL_EXECUTION.md)。本条记录本地阶段，发布和真实验收另行记录。

## 2026-09-26 R1 状态同步与删除前清单

main54ce/部署source72673已核对。PR220的2407 tests/CI/两环境实包读回、F5语义policy PASS和F10合成生命周期PASS归入当前摘要；原strict FAIL、4缺答、2个503 UNKNOWN和所有冻结报告保留。自然试用起点未建立，样本0/0，生产未启用。

9张表当前盘点：2张旧bot-memory精确0/3行（prod全SETTINGS），6张现役业务/V2，1张更早stats候选。旧向量资源清单来自9月23日模板，孤儿候选9月10日证据需刷新，均未执行资源删除。Project/Environment标签ACTIVE，Component INACTIVE；未由标签状态推算实付。

本轮R1仅更新契约/清单/状态/工单和自动任务优先级，未修改运行代码、迁移设置、删除AWS数据/资源或启用新群。PRE独审ALIGNED：用户的新清理前置覆盖旧验收后删；settings与V2媒体必须先解耦；Retain不等于删除；Z18清单交付和Z19功能退役可按限定范围结项，副本责任留Z10。后续POST/CI/发布证据追加。

R1最终POST/maintainer独审ALIGNED；两项发现已修正：F9自然观察不包含在已完成合成阶段内，Z20的停写/保护前置按已满足证据处理，不等待Z01/Z03关闭。20个任务映射及本地链接检查PASS，pre-commit全项PASS。21个GitHub正文/状态与本地镜像逐项读回一致，#175/#178按限定范围关闭，#221新建；automation新增清理前置/同步及R2/R3优先执行，原schedule/target/ACTIVE保持且逐字段读回一致。详见[sync.safe.json](evidence/2026-09-26-retirement/sync.safe.json)。本PR为文档同步，未重跑业务全测试，CI与受控合并另记。

R2/R3补充只读进展：3条旧SETTINGS只含退役开关，无style_profile或现役setter，PRE复审同意取消无意义的死开关迁移，以精确字段/类型/hash再次核验作为退役门，任何变化先停。Project=ZerdeBot本月CE可归属Usage为USD1.2218612373（dev0.4012865637/prod0.8205746736），Estimated、含当日部分、非完整实付；未标记账号费用不归Zerde，账单责任尚未闭合。Z04追加现有AnyIO两项漏洞（8条重复清单告警）定向修复任务；本PR不升级运行依赖。见[followup.safe.json](evidence/2026-09-26-retirement/followup.safe.json)。

settings切换独审补充已纳入：0/3精确字段/类型/hash门禁同时位于取消旧读取的新代码部署前和物理删除前，期间保持停写保护；避免先默认化已改变的style、到删表时才发现。public_replay/plain_requests须随源码解耦共用同一纯normalizer，冻结gold/scorer/run不改。

## 2026-09-27 Z04依赖修复开始（尚未部署）

定向锁AnyIO4.15.1（安全下限4.14.2,<5），其Python<3.15所需typing-extensions4.16.0；其余锁定版本不变。5个导出check通过，实际ARM probe增加AnyIO/httpx导入与版本读回；本地实际socket取消回归及打包契约25通过。升级后全量既有2407项通过（224.93秒）；新增socket取消用例连同HTTP/打包专项25项通过，范围重叠不累加。CI/独审/发布尚待。见[执行契约](ANYIO_RELEASE_EXECUTION.md)。旧源码和资源清理尚未执行，既有学习和预算不改变。

第一候选ad49acfe的CI36265065402两job成功，2408通过；两环境实际ARM/候选独审通过。实际CF changeset进一步发现中文news历史模板ENABLED/现场DISABLED及Quiz ARN→Bot policy动态依赖，故原候选未执行并撤销，追加源码固定停用和单leaf校准契约；旧PASS不替代新head CI和新发布证据。


## 2026-09-27：PR223依赖安全发布完成；Z20源码清理进行中

PR223源码c9a42199、合并b232df6，CI36266070652双job/2409测试通过。AnyIO4.15.1/typing-extensions4.16.0在五个受影响函数实包验证；两环境各六函数/共享层/配置及控制独立读回PASS，workflow ACTIVE。生产中文news声明先从历史ENABLED校准为实际DISABLED，再发布代码，未恢复中文推送。主/独审摘要与指纹见[安全发布证据](evidence/2026-09-27-retirement/anyio-release.safe.json)。

如实保留：首次读回发现AWS Auto将news/quiz换到现有核心函数相同runtime补丁；第二次发现CDK SOURCE地址复用初次上传包，重建pyc包含不同时间戳/临时路径。失败报告未覆盖；所有源文件/锁依赖/pyc语义经独审，再封存实际完整S3 ZIP并逐字读回。dev是事后核验，prod执行前额外核对S3版本/ETag/大小/完整hash。未放宽为忽略pyc。最终收据不是旧INCOMPLETE文件。

Z20按已告知清单开始本地删13模块和当前依赖解耦，18组合成请求基线及PRE、混合测试保留清单已完成；当前不代表新代码发布或云资源删除。旧SETTING瞬时强读工具也已独审，须停读部署前和实际删表前各跑新label；不把原0/3数据当永久事实。无新自然样本、无新生产学习、无新模型调用。

## 2026-09-27 Z20 源码退役：本地实现与独审

13个旧知识/自动互动/历史导入模块及调用已拆除；纯显式context和V2临时媒体保持单一所有权。158个现役测试契约均保留或明确迁移；旧算法测试随算法退役。新增65种旧模块打包复活形态及四语言提示检查。2264项全测通过、pre-commit全通过、正确性和维护性独审ALIGNED；首轮2条旧配置测试失败及修复记录保留。详见[本地安全摘要](evidence/2026-09-27-retirement/source-local.safe.json)。完整18请求对照、CI/ARM/实包和两环境发布尚待，旧表/向量资源未删，不作为Z20完成。

## 2026-09-27 S4资源候选实现

S4资源退役已在当前候选实现：14项/环境旧声明、旧Bot env/IAM、Operations的4个向量告警名及专用indexer入口移除；打包验证改为精确五函数，费用inventory和现役数据owner不变。尚未合并、部署或删除云资源。 定向infra/router/packaging检查130通过，新增费用scope回归后全测2250通过（166.86秒）、pre-commit通过；首轮测试收集残留专用router导入已修复并保留失败日志。云删除数0。见[候选证据](evidence/2026-09-27-retirement/resource-implementation.safe.json)。
