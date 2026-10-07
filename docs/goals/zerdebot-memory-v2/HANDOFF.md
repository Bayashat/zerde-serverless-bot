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

# 当前执行入口

验收根`2026-10-06-explicit-quota-guard`：CURRENT、final-release及独审、artifact-probe/result及independent-post、budget-QuotaGuardFinal20261006A、docs-release及独审。全部已结束build/prepare/hold/merge/execute/readback/finish/probe/reader不可重跑。PR248发布当时唯一时点reader为该目录read_budget_published.py；PR251配置改变后已由上方G reader替代，旧入口不得用于当前配置。文档main不是新Lambda源码。

下一步回到Z01原有限真实业务缺口：以本轮私有NEXT_Z01_GAPS.safe.md为最新本地研究入口（尚非计划PRE/执行），原provider-cost-gaps源码指针作背景，在本次配额门禁实际发布基础上冻结专用dev公开问答/mention/clear Reply场景与现场证据合同、独审后再发消息。仍不重跑18旧schema/F5-F10或旧Quiz题/投票。Groq/DeepSeek待用户登录，无新回复不反复打开登录页；计费缺口UNKNOWN不当0。

原七项UTC职责逐项保持，另新增第八项Oct13 18:26:43.519150本轮失败读回四文件，按failed-dev-download-retention.safe.json和failed-independent-dev-retention.safe.json两份迁移后精确路径/hash人工删除并独审，不按原ledger旧路径删成功轮文件：Oct8 17:13:39.091570日志9原文、Oct11 17:01:48.147210费用9原文、Oct12 17:15:22.532382答案试验247原文/派生、Oct13 08:06:04.659429发票3原文；Oct17 16:20:38旧memory PITR复查、Nov1 11:46:02.425旧memory SYSTEM、Nov2 08:45:11.254旧stats SYSTEM。上述四类原文文件数量只作摘要，按实际ledger逐文件身份/hash执行；不能通配、不能提前、迟延如实记。Oct5 USER与Oct4临时AV已履行不重删；旧三归档/key真实延误保留。文件删除不等于介质安全擦除。

现役6表/业务/凭据/共享层保留，13旧算法/vector与37在线对象退役不重做。原计量/UNKNOWN/epoch不改，dev CONTROL仅观察合法变化，prod无新CONTROL。仅既有Test bots和授权账号；不伪造线上update/阈值/成员/模型，不Invoke/Receive/Purge混合队列；无动作时确认不做验证码踢出风险测试。全部业务/自然/推广/副本责任完成才删除automation。

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
