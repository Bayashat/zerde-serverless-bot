## 当前执行入口（2026-10-06）

先读私有验收根`2026-10-06-provider-cost-gaps/CURRENT.md`、`final.safe.json`、`invoice-independent-post.safe.json`、`docs-release.safe.json`及最终独审。全部原/V2采集与已结束渲染/发布脚本不得重跑；两个登录页面保留等待用户，不反复打开。实际文档交付以最终回执为准，缺回执不推定通过。

下一步：用户登录后，先核实际账号/组织与九月日期口径，再按有限新工具/现场审查读取Groq、DeepSeek报表；在此之前继续其它独立业务工作。AWS付款、历史Free Tier与Google非秘密映射分别有限核验，不能用当前免费额度推历史。原Quiz投票提交未确认的PARTIAL不重做，若另立新验收，先解决能确认提交的原生操作和同update_id证据。当前七项期限见RETAINED_COPIES，Oct8最先到期。原6现役表/控制/预算/UNKNOWN保持，prod记忆不开启。

## 2026-10-06：九月账号发票已核对，供应商登录仍待

有限只读查询取得九月一张AWS账号发票摘要：税前USD38.65、税USD6.18、总USD44.83；三种币种投影均为USD同值，不能相加。原始回执独立复核通过。它属于整个账号，不是Zerde独立费用或已付款证明；此前Zerde标签Usage USD1.4977694507仍按CE原口径单列。CE账号Usage比发票税前多USD0.0074992985，原因未核，不臆定为舍入或强行对齐。

Groq和DeepSeek官方控制台均停在登录页，已交用户登录；没有读取账户账单、密钥或修改支付。两项九月消费仍UNKNOWN，不当零。AWS付款/完整历史Free Tier、Google非秘密运行映射/税与付款仍待；Z17和Epic保持OPEN。本轮原工具在端点校验误停，仅1次STS；V2显式正确端点后1次STS＋1次发票摘要成功，共3次AWS只读，原失败保留，独立POST未新增云调用。这不涵盖后续CI的基础设施只读预览。

[本轮范围与下一步](PROVIDER_COST_GAPS.md)；[安全结果](evidence/2026-10-06-provider-cost-gaps/result.safe.json)。新增3份精确发票采集原文于2026-10-13 08:06:04.659429UTC人工清理并独审，原六项期限不变。没有产品代码/部署/Telegram/模型/控制/预算或付款修改；运行仍PR242，自然0/50有据、0/20未知，production_ready=false。

## 2026-10-05晚：答案重送尝试未确认投票，权限已恢复

此前10月5日晚私有入口：验收根 `2026-10-05-quiz-answer-redelivery` 的CURRENT、final.partial、independent-partial/final、docs-release及最终独审。缺发布回执不推定完成。所有本轮云操作/UI动作均已结束，不重跑once或复点新题。下一步 `NEXT_COST_GAPS.safe.md` 仅研究，先Groq有限只读计划与现场身份确认。

此前该轮六项UTC责任为Oct8 17:13:39.091570日志原文、Oct11 17:01:48.147210费用原文、Oct12 17:15:22.532382本轮Quiz原文人工精确清理；Oct17 16:20:38原PITR复查、Nov1 11:46:02.425旧memory SYSTEM、Nov2 08:45:11.254旧stats SYSTEM到期只读。Oct5唯一USER已完成，不再待删；精确范围由[副本台账](RETAINED_COPIES.md)及各原manifest拥有。

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

# 10月2日发布交接（历史，已结束）

验收根`2026-10-02-sync-invoker-log-fix`：CURRENT、final-release及独审、artifact-probe-v2/result及independent-post（原artifact-probe首轮夹具失败完整冻结），artifact-probe-failed-independent.safe.json、budget-SyncLogFinal20261002A、z02-final-closeout、docs-release及独审。PR242全部build/prepare/hold/merge/execute/readback/finish/probe/reader均已结束，不重跑。运行源码08cc614；文档main不是Lambda构建。部署workflow ACTIVE。原dev post因9559→0aac的两个托管runtime标识差异INCOMPLETE保存在post-main-dev-runtime-incomplete；新V2严格限定目标/对象/Auto整对象并全量重读，不重跑旧post或复用PR240反向旧例外。prod首次STS只读超时原两文件保存在post-main-prod-sts-timeout，新prod_readonly_retry_v1只读入口及独立保全/读回链已结束，不重跑或重部署。当前唯一预算reader为本目录read_budget_published.py，每次唯一label、非持续许可；原计量和UNKNOWN保持。

Z02有限范围已结项；旧CloudWatch FAIL与19未分类原结果不改，原始9文件严格保留到Oct8期限。本段为10月2日交付时的下一步记录；九月费用现已按上方10月4日结果完成有限核对，原next-cost-closeout-draft仅保留为研究历史。旧9/27动态月份脚本不得在10月重跑当成九月；可归项目成本、未标池、税credits、FreeTier和供应商消费/充值/付款分别列，未知保留UNKNOWN，不加Memory估算。其它Z01/Z12-Z16真实业务恢复继续，原Quiz UI PARTIAL不补猜或重发冻结题。

五项UTC职责：Oct5 08:18:35.953唯一旧stats USER人工删除；Oct8 17:13:39.091570九CloudWatch原文人工清理；Oct17 16:20:38原PITR复查；Nov1 11:46:02.425旧memory SYSTEM；Nov2 08:45:11.254旧stats SYSTEM。精确身份/文件由RETAINED_COPIES及各原manifest拥有，提前到场同轮等到期限、单次等待不超60秒，迟延如实记录。Oct4临时AV已履行、旧归档/key真实延误保留，不重建/重删。

仅获准dev Test bots与现有授权账号；不伪造线上update/模型/成员/UNKNOWN、不Invoke、不Receive/Purge混合队列；无人动作时确认不启动验证码踢出风险。dev原CONTROL/epoch仅观察合法变化，prod无新CONTROL。13旧算法/vector入口与37在线旧对象退役不重做，6现役表/业务/层/assets保留。自动社交/历史导入/抽奖不恢复。自然0/50与0/20、起点未建立、production_ready=false，不造聊天/邀人/开新群。完成全部业务/自然/推广/副本职责才删automation。

---

# 历史交接记录

## 2026-09-21：F4/F5 完成，真实群预检发现两个阻碍

PR #215 已合并并部署到 dev/prod；240 场景、480 问题的四语言真实模型合成测量及全文独审通过（来源1176/1176、未知256/256、已知完整220/224）。原严格报告与四个缺答保留，没有改gold。真实群生命周期和七天试点尚未完成。

现场发现 Telegram 注册漏 edited_message、旧 AWS USD 2.70 阈值已暂停可选学习。本次沿原 owner 修复订阅与提升月目标为模型USD70/AWS USD30，保留所有费用与异常保护。当前修改/发布/真实验收见 [本轮记录](LIVE_UNBLOCK_2026_09_21.md)；不能继续以旧F4待发布或F5待复验的历史文字启动重复工作。


## 2026-09-19 当前入口：F3 结束但未通过，F4 本地验证通过待交付

F2 PR #214 已合并，F3 240 场景已记录、480 全文已独审；仍有 1 个未完整执行检查点和 3 段无依据状态/能力表述，整体 INCOMPLETE。原 strict 结果、gold、输出及账本冻结不改。完整数字、费用与证据见 [F3 结果](F3_RESULTS_2026_09_19.md)。

F4 [执行契约](SOURCE_RETRY_EXECUTION.md)已 PRE ALIGNED，代码和针对性回归已实现，POST/correctness/维护性均 ALIGNED，完整 2331 项测试和 hooks 通过；CI及合并发布待执行，尚未新模型复验。继续独审/CI/精确交付，不能开启学习或重复已完成的 F1/F2 发布。累计模型费用责任 USD 19.838358，剩余 USD 80.161642，非实付。

本地 3 个归档及专用密钥已删除且独立核验，实际比期限晚约 5 小时，详见 F3 结果；不重复删除。PITR 10 月 17 日复查及其他副本职责保留。Telegram 记忆生命周期和七天真实单群试点仍待完整质量门槛通过。以下旧时间段仅保留历史，不作为当前待执行状态。


## 2026-09-18 当前入口：F1 已发布，F2 离线测量交付中

F1 [PR #213](https://github.com/Bayashat/zerde-serverless-bot/pull/213) 已合并为 `f6c18b9`，冻结构建 `10e651a` 与合并树一致；CI 35232584331 两项成功、2220测试通过。dev/prod发布、实际包/配置/存储身份读回与独立核验均完成。各环境只更新三个核心函数，学习控制读回无ACTIVE；不重复部署。详见[已发布安全摘要](evidence/2026-09-18-f2/f1-release-summary.safe.json)，它是F1当时快照，不能当作F2或模型质量验收。

F2 新增离线 `semantic_review`：完整枚举学历事实和所有实际回答，按出现位置独立审阅，绑定来源/实际发送/原报告及人工判定指纹；缺审、重复、失败状态或来源失效均不能算通过。已实现并通过81项故障测试，最终独审/CI见本次交付证据。[详细契约与CLI](SEMANTIC_REVIEW_CONTRACT.md)。这只改变开发验收工具，生产代码、基础设施、旧gold/scorer及已完成run均不变，无需重新部署Lambda。

下一步完成F2交付门禁，再由新会话启动器在首个模型调用前冻结源码、policy和独立reviewer登记；新目录完整执行240场景及全文独审。旧public-v25继续FINISHED/质量FAIL，禁止resume。历史费用责任USD19.639943保留，新会话上限USD80.360057；不是实付账单。真实Telegram记忆闭环与七天试点仍未开始，学习保持STOPPED。本地备份2026-09-18 21:49:52 Almaty到期职责独立不变。

## 2026-09-17 F1 本地代码修复完成（历史，已由上方发布记录取代）

`self-claims-v2.6` 已在原worker/extractor/writer修复完整短源证据和称呼原文保真；长源及跨引用来源保持PENDING，24小时无模型复检，原期限不变。同批短源继续，不能把待处理项当学会。独立POST/correctness与maintainability均ALIGNED，完整回归2214通过后，最终Unicode边界/更正专项180通过；不同测试范围不累加。详见[代码证据](evidence/2026-09-17-f1-code/verification.json)和[执行契约](QUALITY_FIX_EXECUTION.md)。当前尚未新部署或运行模型，学习仍不启用；旧240场景FAIL和全部费用责任保持。下一步CI与实包发布；F2逐项语义测量仍待实现和冻结，再新会话真实复验。原9月18日21:49:52 Almaty备份期限不变。

## 2026-09-16 当前入口

完整真实模型运行与240场景逐文复核已完成，质量门槛仍未通过；不再恢复已完成public-v25。当前细节、原始分数、真实缺口和下一步F1–F4见 [全量评估与修复契约](FULL_EVALUATION_2026_09_16.md)。dev/prod学习现场强一致读回仍默认STOPPED；Telegram生命周期及七天试点未开始。旧备份原到期职责不变。下方为历史发布记录，不代表模型进程仍运行。

## 2026-09-15 最新进度（优先于下方历史记录）

第一批发布已完成：#205、#206、#207、#210 已合并，main `5669a71` 已部署 dev/prod。两环境六个实际 Lambda ZIP、共享层、依赖锁和配置读回通过；测试群真实 `/ping` 和 `/ask` 成功。生产旧摘要定时器已从基础设施移除，中文新闻的原停用状态保持。

清零后的18条旧任务已在生产两入口同步回放，全部丢弃；独立前后核验旧记忆0、向量0、3条原业务SETTINGS完整哈希不变。旧表和空索引资源仍保留；9月18日备份到期、PITR复查和Z18未授权资源删除边界不变。见 [发布证据](evidence/2026-09-15-continuation/deployment-5669a71.json) 与 [独立回放证据](evidence/2026-09-15-continuation/independent-release-and-replay.safe.json)。

新版修复 [PR #211](https://github.com/Bayashat/zerde-serverless-bot/pull/211) 已 squash 合并为 main `5ce82d1bbe09176b8eeecaddbffa95b3afa6a4ef`。首个合并方式因仓库只允许 squash 而被拒绝，未产生合并；随后使用同一审阅 head `667e6c9` 成功，父提交及完整树已核对，部署 workflow 已恢复。CI `34904175265` 两项 SUCCESS，完整测试2,179项通过（397.97秒）；公共恢复与安全独立74/69项是不同范围，不累加。冻结构建/评估源码为 `9158201`，与合并结果的差异只有三份文档和一份测试。**本次dev/prod最终部署读回及独立复核均通过：各六个实际Lambda包、共享层、锁定依赖与完整配置匹配，三条映射及21项受保护存储身份保持。** dev一个、prod四个精确CONTROL键强读缺行，学习默认STOPPED；生产旧写入Deny和中文新闻既有停用状态不变。 见 [本轮状态与指纹](evidence/2026-09-15-continuation/public-v25-release.json)。

第二阶段未完成：冻结真实基线155个场景提交（152 EXECUTED、3 UNSUPPORTED），其余85保留未提交分母；供应商实际dev密钥已确认每天500请求的免费层用尽。新 `public-v1 / self-claims-v2.5` 的240场景评估尚未启动，不能声称有模型在后台运行。原run/账本/gold不改。新版公共问答回放、限流暂停/恢复及已发现的记忆质量修复见 [当前契约](../../MEMORY_PUBLIC_EVALUATION.md)，需待配额恢复后按冻结源码和同一新会话完成四语言复验。不要把旧report/provenance的首场景smoke当作全量报告；使用[冻结独立摘要](evidence/2026-09-15-continuation/real-model-paused-summary.json)。

十账本[增量回执](evidence/2026-09-15-continuation/ten-ledger-reconciliation.json)保留816次尝试的总费用责任USD18.977963，其中明确用量标准价USD0.169131、其余为未知预留；不是实付账单。新会话上限USD81.022037，与旧责任合计USD100。私有启动器以只读账本门禁拒绝缺失、空、symlink、错误配置/结构，取密钥前停止；合法 `INFLIGHT` 保留原预留。28项临时SQLite回归及独立同28项通过，实际本地check为0 SDK/模型调用，旧十账本与冻结源码未变。冻结指纹见本轮证据；不得空建丢失账本或另开目录重复获得预算。

第三阶段仍未开始：学习STOPPED；待完整模型门槛、真实Telegram来源/编辑/更正/遗忘/退出闭环通过后，再开启单群至少七天及真实样本验收。显式问答继续可用，旧记忆、抽奖和自动社交不恢复。


## 2026-09-15 首次完整发布前历史快照

本节记录当时尚未发布的状态，已由最上方最新进度取代；不作为继续合并、部署或运行旧评估器的指令。

先读 [CONTINUATION](CONTINUATION.md) 的最新授权、预算与三个执行阶段。#205、#206、#207 已分别在最新 main 上通过代码检查和基础设施预览后合并；合并提交为 `e1a4c3c`、`56f1541`、`cf93b74`。部署 workflow 已恢复 ACTIVE，分支保护未改。本次下述 Groq 恢复修复和评估预算扩展正在单独交付；此刻尚未执行本轮完整 CDK 部署，不能把合并视为上线。

组合源码的 2,091 项测试通过；实际 dev/prod 打包及各六个 ARM 导入探针通过，云端变更尚待最终 main 产物与 change set 核验。预计生产仅更新三个同源 Bot 包、删除已退役摘要规则及其发送授权；开发仅更新三个包并移除退役环境默认值。现有中文新闻停用状态、旧存储写入围栏、业务资源和计费起点须保持。

真实 Groq 合成契约证据见 [37 次实际调用及全部失败记录](evidence/2026-09-15-continuation/spam-provider-contract.json)。分类响应损坏时仅允许一次严格结构化恢复，总时限 16 秒；其他错误仍保留原重试语义。小样本不代表完整反垃圾质量验收。

新版冻结的四语言 240 场景 Gemini 评估正在运行，旧 56/240 基线与全部费用责任记录原样保留。首个 kk 切片仍有来源跨度和无记忆公开回答路径的验收缺口，不能宣布整体通过；不修改 gold 或用删除样本提高成绩。两环境各精确群控制键当前均缺行，学习默认 STOPPED。真实测试群来源/生命周期、清零后旧任务回放及七天试点仍须完成，试点尚未开始。原备份到期任务独立保留。

以下为 9 月 12 日发布后的历史交接快照，其“仍待审阅”等时态已由本节更新；具体删除结果和保留期限继续有效。

## 2026-09-12 历史发布快照

当前阶段是 **DEPLOYED / ONLINE_CLEAN_COPIES_PENDING / LEARNING_STOPPED / ACCEPTANCE_INCOMPLETE**。首次[集成 PR #204](https://github.com/Bayashat/zerde-serverless-bot/pull/204)的发布基线为 `f305aae911fffd652b225e6aecd9eded495e2d1a`。用户随后明确授权合并部署费用修复；#208、#209已合入，当前main为 `e0780520dad8f19039b4a640bbf10489fd292210`。生产Bot、旧vector入口和Memory worker三个同源代码包已更新并实际读回；News、Quiz、Operations仍为已核验的f305代码，共享Layer17不变。正常业务保持，四群学习STOPPED，抽奖和旧自动社交入口仍退役。

先读 [LIVE_ACCEPTANCE](LIVE_ACCEPTANCE.md) 的最新现场记录，再读 [PLAN](PLAN.md)、[TASKS](TASKS.md)、[EVIDENCE](EVIDENCE.md)。旧独立 PR 的代码已通过 #204 集成；不要重复合入早期依赖分支。后续修复 [#205](https://github.com/Bayashat/zerde-serverless-bot/pull/205)（dev 并发、环境容量与旧摘要规则）、[#206](https://github.com/Bayashat/zerde-serverless-bot/pull/206)（固定清单续跑）、[#207](https://github.com/Bayashat/zerde-serverless-bot/pull/207)（真实模型接口、评估与两项质量修复）仍待审阅。[#208](https://github.com/Bayashat/zerde-serverless-bot/pull/208)（标准队列费用读取、恢复错误日志与正常历史追赶）和[#209](https://github.com/Bayashat/zerde-serverless-bot/pull/209)（逐执行配对与重试计费）已合并部署，详见[本次发布证据](evidence/2026-09-12-post-merge/cost-monitor-release.json)。旧摘要仍显式DISABLED。

真实 Gemini 基线56/240场景执行，其余184因预算暂停保留UNSUPPORTED，尚未获得其他三语言的实际模型样本。已发现真实字段选择和安全误拦问题，修复及真实调用工具在PR #207，全量1,906项本地测试通过；尚未重新取得修复后的模型质量证据，也不等同已部署版本。不得因合成测试或有限真模型样本通过而启用生产学习。

生产旧表/向量写入围栏已生效并通过负探针，18条旧任务在清理前实际回放均无效；清理后回放尚未执行。**9月12日16:20:47 UTC独立只读终检已确认在线清零**：旧表只剩原3条SETTINGS且hash不变，旧记忆目标和向量均为0；旧表和空索引资源仍保留。加密备份、PITR等保留副本尚未物理清除。单群七天试运行未开始；无长期记忆显式问答保持可用。在线清零、副本消退和产品质量分别验收，详见[最终证据](evidence/2026-09-12-post-merge/cleanup-independent-final.json)。

## 已有实现

- Z01–Z04：自动互动停用、旧记忆隔离、日志脱敏、删除白名单、可复现打包和依赖安全升级。
- Z05–Z09：独立表、唯一事实 writer、可靠消息摄取/恢复、结构化抽取、当前有效事实档案、有来源问答、群话题样本、更正/遗忘/退出、编辑失效与发送前复验。
- Z19：抽奖命令、观察、存储和定时恢复已退役，两类旧TTL任务无副作用消费；已核验旧表在线残留清除，状态为`runtime_retired_online_residue_cleared`。原#181已被退役方向取代，不恢复抽奖验收；保留副本和整体验收未完成，工单未因此关闭。
- Z10：同一manifest/备份下完成30,794条旧记忆与8,259条旧向量的在线清零，原3条SETTINGS完整。诊断controller六轮于15:48:31 UTC完成，16:20:47 UTC独立终检通过，状态为`online_clean_copies_pending`。先前未知停止的历史及原因UNKNOWN仍保留，不用后来成功倒推根因。
- Z11：四语言合成语料、独立评分器和真实领域代码离线回放。固定假 provider 只测试工程链路；不能当作 Gemini 质量证据。
- Z12–Z16：验证码、反垃圾、Voteban、News、Quiz 修复，已在共享入口组合验证。
- Z17–Z18：告警/恢复通知、dev 按需开关、模型预留、AWS 计量/监控和旧资源清理手册。资源标签已随模板部署；Project/Environment成本分配标签已激活并读回，真实通知已有应用确认；持续旧告警已由root补发并取得应用发送确认；费用修复三次实际验证后，可统计的历史用量覆盖补齐至9月12日22:05 UTC，状态ESTIMATE_VERIFIED，新增Memory AWS的dev/prod合计目录价保守估算为USD1.768707。非零共享WRU/SQS已有历史样本；项目实付账单、Free Tier与完整费用验收仍开放，Z18云资源销毁未执行。

## 审阅与合入

历史独立 PR 在 TASKS 中，对应源码已通过最终集成#204合并。#205–#211均已合入，不再依次合入旧分支。#205–#207/#210的完整CDK发布已有`5669a71`读回证据；#211也已取得两环境最终实际读回及独立复核；真实模型质量继续单独验收。

以下依赖 anchor 仅解释历史审阅 diff：`feat/zerde-reviewed-foundation` → `feat/zerde-memory-v2-foundation` → `feat/zerde-memory-v2-answer-foundation`。它们包含多个当时的模块快照，现在不再作为待合入发布分支。后续发布仍须重新记录 SHA 和真实产物 hash。

用户后续授权已覆盖本轮具体发布、必要测试与原计划的旧记忆清零；不能继续套用合并前的只读限制。保持精确清单、停写、备份及条件删除边界。Z18非记忆旧云资源销毁仍单独列范围，不借本轮测试扩大删除。

现有`.github/workflows/deploy.yml`合并main自动部署dev，prod手动。9月12日仅代码更新留下的CloudFormation指针差异，已由9月15日`5669a71`完整CDK发布同步；不得再以此历史状态误挡已授权发布。后续仍须核对最新模板、实际包/配置与已保护的中文新闻停用状态；两环境首次V2计费起点1789134091不得重置，旧表/index写入Deny围栏保持。本轮#211在合并窗口短暂停用deploy workflow后已恢复，最新部署结果以各环境实际读回为准。

诊断续跑沿用原manifest和原绝对截止，六轮完成后已退出；9月12日16:20 UTC独立终检当时确认无操作进程/锁、原运行版本/环境/写入围栏不变、四个精确CONTROL键强读缺行，学习保持默认STOPPED。不要重新启动已完成的controller或重复终检。原启动与中断记录保留在[诊断阶段证据](evidence/2026-09-12-post-merge/cleanup-diagnostic-continuation.json)和现场时间线中。

终检后，root于9月12日 **16:23:16 UTC**恢复原本地任务`zerde`的每日备份到期职责；9月15日因应用每线程只允许一个自动任务，验收跟进已加入同一任务。每天 **12:49:52 / 21:49:52 Asia/Almaty** 分别兼顾配额恢复后的验收与原到期职责，不能把一项完成当作取消另一项的理由。三份加密归档、原manifest/backup和独立密钥仍按原范围管理；到期清理尚未执行。原归档在 **9月18日16:49:52 UTC（Almaty 21:49:52）**到期，不延长；旧表实际PITR窗口35天，保守复查点 **10月17日16:20:38 UTC**不是物理删除承诺。日志、队列和其他副本分别跟踪；执行依赖本机及Codex运行。Z18非记忆旧云资源未销毁，保留的旧表和空索引不算资源已删除。

## 下一阶段仍需完成的真实证据

1. **从已验证发布继续验收。** #205–#211均已合并，当前main为`5ce82d1`；本轮冻结`9158201`与最终main运行源码等价，两环境各六包、依赖、共享层、配置和控制状态已实际读回并独立通过。不重复部署或合入旧分支；配额恢复后按下述质量/生命周期顺序继续。
2. **冻结配置并先保持学习 STOPPED。** 两环境成本计费起点相同，覆盖首次 V2 专属资源部署；不能用之后启用学习的日期掩盖早期费用。原始内容保留30天；dev 默认不消费；队列、超时、IAM、日志、告警接收人和共享预算表要读回。缺控制/计费许可时默认不学习。
3. **完成真实模型与评估证据。** 先独立复核合成 gold 的语言及事实标签，再使用实际 Gemini 输入/usage/输出形成独立 observations。固定 fixture 的分数不是模型效果。不得复制 gold、以全拒答满足来源100%，或因超时/预算暂停跳过样本后宣称完整覆盖。known 问题完整回答召回每语言至少90%，是防止原召回目标被空答绕过的测量补齐。
4. **dev canary。** 验证 Telegram 成员/管理员权限、每条来源链接、真实预算通知、Logs Insights 查询和用量归因，以及验证码、反垃圾、投票、News、Quiz 和显式媒体。恢复路径在真实依赖故障下的结果与合成测试分开记录。
5. **完成保留副本的后续验收。** 在线清零已独立通过，不再重跑本次删除或重新plan/backup。保留原manifest `67c71ec9bd6e62b43fd519a8b427f286dd81661a415f356912703db27f26e8f4`、执行与终检证据，按原9月18日到期职责处理本地密文和独立密钥；PITR在10月17日保守时间点之后实际复查，不能提前宣称物理清除。日志/DLQ/PITR/备份分别验收，3条设置所在表和空向量索引继续保留。Z10、Z19工单及整体验收不因此自动关闭；Z18其他资源仍需独立明确范围。
6. **单群启用与推广。** 9月15日清理后的18条旧任务回放和前后数据核对已通过，不重复清零或恢复旧controller。前述质量、生命周期、部署和成本门槛通过后，只为获准的试点群建立新学习epoch。收集至少七天、50个有依据回答和20个未知问题，逐语言统计质量、零容忍、延迟和覆盖。样本不足继续保留Z11开放；达标后再按授权范围推广。

在线清零已完成，生产单群学习仍须等待真实质量、控制、成本与部署核验通过，不能由清理完成自动建立新epoch。AWS成本起点和群学习时间仍是两个独立边界。

## 配置读回清单

- `MEMORY_COST_METERING_STARTED_AT`：唯一新增手填计费起点，dev/prod相同。CDK注入的表/队列/共享费用账本/topic/schema/解析后inventory hash不另建同名人工配置来源。
- `DEV_RUNTIME_ENABLED=false`：默认关闭六个Lambda执行、三条SQS映射和恢复调度；dev canary需明确启用并核对积压及Telegram环境隔离。启停不会自动改变群学习控制记录。
- `ADMIN_USER_ID`：当前单一私聊接收人，正整数，需先私聊bot。核对SSM权限；News/Quiz专用群配置为空时会回退共享 `CHATS_*`，不能误发到生产群。
- Memory worker120秒、并发2、队列可见740秒；日志七天；prod Quiz与V2表PITR七天，dev关闭。恢复演练用新表验证，不能覆盖现表。实际Lambda环境变量必须低于4KiB。
- 活跃环境各22个告警，dev停用为0；两个环境都启用则44。成本inventory的10仅是两环境新增Memory告警预留，不是总告警数。需实测告警、恢复及通知失败路径到管理员。
- 真实成本门槛包括逐执行START/Final/REPORT关联及同RequestId重试、完整时间覆盖和暂停恢复。本轮10小时20分钟历史窗口取得worker dev/prod 117/94次、共享Bot dev/prod 5/18次及非零WRU/SQS证据；三次生产验证补齐可统计的历史用量，但未做一小时持续观察。Project/Environment成本分配标签已激活；目录价估算不是项目实付金额，Z17账单归属与整体费用验收仍开放。

## 失败时恢复

回退到无长期记忆的显式问答，保留删除/来源栅栏与旧任务退休；不恢复旧 profile、摘要、向量或自动社交。未知 Telegram 发送结果保留 UNKNOWN，通过恢复/核对处理，不能盲目重发。

预算暂停仍保留短期来源准入、恢复与控制，因此仍有 AWS 消耗。$70模型预留是调用前控制；$30AWS是保守估算与停止可选工作的目标，不是账号账单硬封顶。按月使用/credits/税/净计费和项目归属证据分别记录。

## 本地重现入口

在完整集成分支运行：

```text
uv sync --frozen --python 3.13.6
uv run --frozen --python 3.13.6 pytest -q tests
uv run --frozen --python 3.13.6 pre-commit run --all-files
```

真实打包、离线回放及清理工具命令分别见 `scripts/verify_lambda_bundles.py`、`docs/MEMORY_V2_EVALUATION.md`、`docs/legacy-memory-cleanup.md`。不要运行旧历史导入。离线回放报告应保留 provider 类型、源码/fixture hash 和失败分项；数值 FAIL 的退出码2不能误报为执行崩溃或“测试通过”。
