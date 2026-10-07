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

Z20的已声明源码与在线资源范围、Z02原批准日志边界已限定结项；Z01最终业务回归、Z12–Z16实际恢复、Z17真实费用归因仍OPEN。下一步优先核对九月完整账期费用，再继续可独立推进的业务验收，不只等待空测试群。自然使用起点未建立，0/50有据和0/20未知；至少7天实际使用及逐条来源/完整答案门槛仍未达到，production_ready=false，不启用新群或prod记忆。

当前运行构建源`08cc614a2f61d9001f3e2a77b9d9e6a7c73585df`（PR242），实际发布证据见上方；PR240与PR235为此前发布证据；PR232记录为此前发布证据；9月28日资源清理当时没有新Lambda部署。F5语义policy PASS、来源1176/1176、未知256/256、已知220/224；原strict FAIL、4预算缺答、UNKNOWN和全部冻结F5–F10证据保持，不复跑或算作自然样本。

副本独立跟踪：CloudWatch九份原文于2026-10-08 17:13:39.091570 UTC精确清理并独审；旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。

[本批实际证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)；[副本台账](RETAINED_COPIES.md)。保留6张现役表、必要业务队列/日志/恢复数据、层/assets和当前凭据；不代表账号全资源已清空。

费用线最近归档仅是9月27日CE项目标签Estimated USD1.2690103981；未标记/共享、credits/税及模型账单仍需闭合。预算账本、未知责任与实际账单分开，应用预算不是账号硬封顶。此前在线退役批次没有模型或支付动作；9月28日晚Quiz验收有真实生成请求，无充值或支付设置变更。

## 工单

- [ ] Z01 #158 — FIX: 停用自动互动并隔离旧记忆路径
- [x] Z02 #159 — FIX: 日志脱敏和 Telegram 内容最小化（原批准范围结项；原文保留期责任继续）
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
