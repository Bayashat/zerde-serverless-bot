# 执行证据

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
