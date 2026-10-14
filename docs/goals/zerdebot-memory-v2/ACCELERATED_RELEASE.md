# Memory V2 有限首发实施计划

**Intent:** 按用户 2026-10-14 直接修订，尽快完成 Memory V2 必要验收并启用现有四个生产群。
**Current Behavior:** Memory V2 运行代码已部署，原正式质量阶段仍未开始；生产群未首次激活。旧计划将长周期自然验收与最终结项绑定，最近工作集中于副本期限。
**Expected Outcome:** 当前部署通过发布前安全与功能检查后，四个已有生产群逐群开启新消息学习与有来源问答；长期质量、费用完整归因和副本责任继续在发布后追踪。
**Target-Perspective Output:** 现有 dev Test bots 中可观察新的来源学习、回答与来源、来源遗忘失效；四个明确生产群实际控制记录 ACTIVE/learning_enabled 且具备真实起点，用户收到明确的首发状态和关闭方式。
**Truth Owner:** task_manifest 仍是工单状态唯一来源；MemoryRepository 是 CONTROL/source 唯一 owner，MemoryLifecycle 管删除，MemoryBudgetRepository 管预算。首发与长期产品质量完成分别记录。
**Contract Boundary:** 当前实际组合部署与共享预算 -> 有限 dev 真实输入 -> 当前来源/问答/删除证据 -> 四群首次条件激活 -> 独立读回。
**Cutover:** 本修订优先于旧计划中将七天、50/20 自然样本、全部独立业务故障场景、完整账单和备份到期作为 Memory V2 首发等待条件的顺序。旧报告、失败、UNKNOWN 和样本数字不改写。
**Displaced Path:** 取消“先等所有开放工单和备份结束才首发”的执行顺序；不新增事实/预算/控制 owner，不恢复旧自动互动、向量、历史导入或抽奖。
**Value Density:** 复用已部署实现和已完成证据；只验证当前改变的绑定和首发实际链。不为源码未变重新部署，不重跑冻结 F5/F6/F7/F8/F10 或旧 once。
**Acceptance Evidence:** 当前定向和完整离线测试；实际包/配置对应的安全回执与新配置读回；有限 dev 原生输入与持久来源/回答/删除；四群串行条件激活及独立强读；原期限跟踪保留。
**Evidence Lane:** LOCAL_TESTED、DEV_LIVE_VERIFIED、RELEASED_OBSERVING、NATURAL_QUALITY_PENDING、RETENTION_PENDING 独立记录。初始自然计数仍 0/50 和 0/20，原 production_ready=false 不冒充自然质量达标。
**Kill Criteria:** 身份错误、跨群/敏感泄漏、来源遗忘后复活、业务误删、配置目标偏差或预算不许可即停止对应现场/启用。一般预算/质量问题可暂停 learning_enabled；身份/泄漏/来源安全故障必须通过现有 MemoryRepository.begin_group_stop(expected_revision) 条件转换为 STOPPING，停止新学习与记忆读取/发送并等待现有租约排空。保留原 epoch 和数据，不调用会创建 PURGE 的 MemoryLifecycle.begin(group)，不自动恢复或另建 epoch。
**Architecture Slice:** src/bot/services/memory_v2/{repository,public_commands,lifecycle,answers,ingestion}.py，services/memory_budget.py，当前 Bot/Memory PR257、Ops PR263、身份 PR251；新本地有限 launch operator 只组合现有 owner，冻结旧工具。
**Plan Review Gate:** 新 PRE 独立审查后执行新云/现场/控制写入口；现有离线测试和只读代码研究可先进行。

## 用户范围与时间

- 首发目标由用户指定为 AWS 当前 Quiz/News 对应的四个现有生产群：1 个中文、3 个哈萨克语。先核 Bot CHAT_LANG_MAP、News/Quiz 配置的实际一致性并保存非秘密投影；不创建群、不邀请人、不按猜测 ID 激活。中文 News 原 DISABLED 状态不改变。
- 用户从现在开始提供多个 Telegram 独占测试段。每段实际开始时记录真实 UTC、原回复 hash、具体 dev 群与不超过 900 秒的结束时刻；段内先核账号/群/空草稿。不篡改旧 H/N UI_STOP，不续发旧草稿，不操作其它聊天。上下文变化即停。
- 生产目标只启用 Memory V2，不向生产群发送合成聊天或重放旧消息。发布后使用正常真实流量观察；无流量时报告缺样本。
- 运行授权、CI/合并和 dev/prod 发布沿既有授权；本用户修订明确授权四群 Memory V2 首发。未知资源与费用/凭据变更不在范围。

## 发布前必须完成

1. 复核实际 main、进程和占用，使用独立分支；针对当前 Memory/explicit/budget 安全代码跑离线回归，再跑一次完整套件。只修真实阻断项，新增测试覆盖实际缺口，不为报告工具制造大量镜像测试。
2. 新组合绑定继承 S 的 19 份安全发布回执和 104 个费用相关源文件/实际 ZIP 校验，并叠加 PR263 当前 Ops 包、已接受 dev DisableRollback 历史偏差和不变 Bot/Memory/身份的实际主独证据。禁止读取、复制、延期 S snapshot。新现场工具采用安全投影，不继续依赖将到期的旧业务快照。
3. 新只读预检限账户/region、目标 Lambda 配置与状态、表身份、四群与既有 dev CONTROL、共享预算。禁止 SSM/Secrets 读取、Lambda Invoke、混合队列 Receive/Purge、全表业务扫描。实际参数及调用上限在工具中封闭，拒绝意外操作。
4. 真实采集前建立本批七日原文账本，起点为首次真实采集，所有后续原文/含原文派生同一期限；文件 0600、目录 0700，立即登记 Z10 与 automation。只有新实际采集才产生新期限。
5. dev 新最小 canary 使用现有 Test bots 与原 owner：新明确自述来源 -> 持久有效事实/有来源回答 -> 对本批来源执行遗忘 -> 新鲜读确认来源/派生不可用。保留原 dev epoch，不对整个用户/群 forget、不覆盖旧档案。原已通过普通 ask/mention/Reply 证据可复用，未证明的部分如实标明。具体输入/来源键/成本和终止条件在现场工具 PRE 固定，禁止用合成原文冒充自然样本。
6. 未完成媒体相册场景只按原两图+一次原生 Reply 的有限合同执行：三个输入身份、同 album、双 ready 后 360 秒无主动回答、精确 caption 父目标、两图真实模型链及语义、单回答 SENT/lease、独立 POST。若无法完成，明确标为媒体发布后待验证，不将其伪装 PASS；首发 Memory V2 文本学习不依赖媒体长期学习（后者不在产品范围）。
7. 四生产群逐群使用实际部署相同的 MemoryRepository.activate_group(chat_id, expected_revision) 创建初始控制；仅初始缺 CONTROL/STOPPED revision0 且无旧 V2 工作/事实的既定群可首激活，检查原切换清理证据。先保存真实意图再唯一条件写，读回新真实 epoch/learning_started_at；未知写结果先只读核对，禁止盲重试/二次激活。遇到既有控制记录先保全并按其当前状态另核，不将新指令用于重置历史。
8. 每群即时读回、组合部署保护与共享预算核验；独立 verifier 读取同四 CONTROL 与配置，不使用主代理自报代替实际结果。正常 off 只暂停学习、已存事实仍可读；安全回退使用 begin_group_stop 的 STOPPING 围栏，保持原 epoch/资料，不创建 PURGE，排空租约后才确认停止。恢复另审，不能把 set_learning_enabled(False) 冒充阻止记忆读取。

## 发布后观察与独立任务

- 七天自然使用、50 有来源/20 未知样本、语言切片、来源正确性和学习/恢复延迟分布改为发布后观察目标；不伪造起点或合成达标。观察起点只能来自真实启用和真实使用记录。
- 发布后第 3 天和每周检查错误、预算、来源/删除风险与可获得真实样本；缺样本记缺样本，不造聊天。更新既有 zerde automation，不另建重复任务；首次发布未完成前不写“已上线”。
- Z12–Z16 验证码/反垃圾/Voteban/News/Quiz 的独立异常矩阵继续开放，已知 Groq HTTP413 另修；如发现影响 Memory 摄取安全的真实缺陷仍阻断发布。
- 完整费用实付/税/供应商登录、八项原副本期限独立保留，不作为首发等待项。原 Oct14 两时点不合并、不提前、不故意拖晚，不并行 UI/发布/删除。

## 执行任务板

|任务|Owner|允许文件/动作|证据|依赖|并行|
|---|---|---|---|---|---|
|T1 当前代码/测试/入口映射|主+只读 explorer|既有测试，launch 本地证据|当前结果与具体缺口|无|只读审查可并行|
|T2 新组合绑定与只读预检工具|主，独立 correctness/maintenance|新 launch 目录；不修改 S/Z/A 原回执|实际 hash/当前配置/预算/四群|PRE|云串行|
|T3 dev 最小真实链|主，独立 verifier|唯一 dev 群、本批精确来源与原文账本|原生输入+持久数据+遗忘|T2，实际窗口|UI 串行|
|T4 四群首次启用|主，独立 verifier|原 MemoryRepository、精确四 CONTROL|一次意图/条件写/新鲜主独读回|T3，预算允许|逐群串行|
|T5 文档/工单/自动任务交接|主，独立双审|当前计划/台账/证据/有变化工单|准确区分首发、待观察、其它待办|实际阶段|发布串行|

本计划不意味着任何新线上动作已执行；实际状态以本批回执为准。
