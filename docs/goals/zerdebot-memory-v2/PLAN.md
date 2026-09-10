# ZerdeBot 可靠性修复与 Memory V2 实施计划

**Intent:** 让机器人可靠地记住成员在本群的明确自述、维护当前事实，并在被明确询问时给出有来源的回答。
**Current Behavior:** 正则 profile、长期事实、摘要、向量存在重复知识来源；旧任务及删除生命周期不完整；生产原文保留 3650 天。
**Expected Outcome:** 所有自动社交互动停止；新 epoch 之后的消息成为唯一学习来源；旧记忆在线不可用并按清单清除；业务功能保持可用。
**Target-Perspective Output:** 成员可查看、更正、遗忘或停止记录；同群问答附证据和时间；不知道时明确表达；管理员收到实际故障、恢复和预算通知。
**Truth Owner:** Memory V2 独立 DynamoDB 表及唯一 fact writer。Profile 是有效 facts 的只读投影。既有 contest repository 继续拥有抽奖业务状态。
**Contract Boundary:** Telegram source identity/revision -> durable pending work -> structured facts -> live source validation -> explicit answer。
**Cutover:** 停止旧 writer/reader/import/backfill/schedules，隔离旧任务并等待在途执行结束；清单备份和按类型清理；验收后逐群启用新 epoch。
**Displaced Path:** 旧正则 profile 写入、规则失败补事实、旧 memory retrieval/vector fallback、主动插话/reaction/channel comments。
**Value Density:** 保留 Python/Lambda/SQS/DynamoDB；一张新表、一个 fact writer、一条 memory queue/worker、一个 outbox recovery 入口。
**Acceptance Evidence:** 分层多语言 gold evaluation、故障注入、dev 行为验收、真实群至少七天观察及数量/来源/成本/删除证据。
**Evidence Lane:** 本地、构建、部署读回、合成 canary、真实产品样本分别记录，不能相互替代。
**Kill Criteria:** V1 不启用向量，不保留旧知识读写作为 fallback；新版失败回退无长期记忆问答。首版验收后删除旧并行实现。
**Architecture Slice:** Telegram/shared logging/explicit ask 接现有 bot；新 memory 域独立；captcha/moderation/votes/news/quiz 独立修复；infra/workflows 统一集成。
**Plan Review Gate:** PRE 已在 2026-09-10 会话独立复查并 ALIGNED；用户明确批准执行。每张实现 PR 仍需 POST/correctness/maintainability review。

## 1. 已批准的产品边界

- 停止普通群聊插话、ambient reactions、频道帖自动评论和 reactions。保留 /ask、直接 @mention、明确回复 bot 的问答及现有业务能力。
- 个人事实只来自本人明确自述；各群独立。身份为 `(chat_id, telegram_user_id)`，昵称是别名，不可按名字合并。
- 同群成员可查询其他成员在本群的非敏感自述，附来源和时间。本人可查看、更正、遗忘、optout/optin。
- 原始聊天保留 30 天，最小事实证据随事实维护；被替代事实历史最多 90 天。职业、城市、当前项目 180 天未确认只能表述为“上次提到”。
- 群规则/共同决定须管理员明确确认；七天话题趋势每日确定性聚合，保留 30 天，不推断性格、关系或成员角色。
- 清零所有旧记忆（历史导入及实时积累），保护其他业务数据；不删除用户本地 Telegram 导出。
- 新增记忆目标每月 USD 10，管理员 Telegram 私聊接收故障/恢复/预算异常，不向群广播。

## 2. 数据及接口契约

### 唯一控制与事实存储

Memory V2 表拥有 learning_enabled、epoch、learning_started_at、subject generation、optout 与删除控制。旧 SETTINGS 仅保留其他业务设置；所有 memory 命令使用同一个 V2 控制接口。

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

UTC 自然月：USD 7 模型硬计数上限 + USD 3 新增 AWS 用量预留。抽取、每次重试、携带 V2 facts 的整个问答调用都计入模型预算，避免不可靠的增量 token 分摊。每次请求按价格版本、输入保守上界、最大输出预留；结果不明不直接释放。

预算耗尽停学习和记忆增强；无长期记忆 ask（排除旧记忆答案线程）、确定性 profile、纠错/遗忘继续可用。群趋势不用 LLM。AWS 使用预估量、80% 提醒、90% 停可选新增工作；AWS Budget 不是账号硬止付，原有无记忆功能费用单列。

观测包含接收/拒绝/已处理/待处理/过期数量、学习延迟、来源支持、删除完成状态、模型 token 和预留、AWS 估算与实际可归属费用。通知只发故障、恢复、预算异常，私聊 ADMIN_USER_ID；先验证通知渠道可达。

## 3. 旧数据清零及上线

1. 部署 Z01 guard：停止所有旧 reader/writer/import/backfill/schedule；旧 memory/summary/vector/proactive/reaction 和 legacy ask payload 全部 no-op。保留 captcha/spam/contest 等业务任务。
2. 等待旧 invocation 退出，核对队列状态；生成精确 DynamoDB key/vector key 清理 manifest、类型计数和业务保护校验。执行时重新读取，不用审计快照当删除名单。
3. 本地加密备份精确范围数据和向量 key，限七天保留，登记删除日期。禁止把正文/个人标识/secret 放 GitHub、日志或 EVIDENCE。
4. 允许清理 MSG/MEDIA_GROUP/USER/USERNAME/EVENT/USER_FACT/GROUP_FACT/JOKE/DAILY_SUMMARY/TERM/AGENT_REPLY/AMBIENT_REACTION/PROACTIVE/VECTOR_BACKFILL 及确认为记忆的 BOT_COMMITMENT/BOT_CORRECTION。保留 SETTINGS、CONTEST、CONTEST_RULE、CONTEST_TTL_OUTBOX 和其他业务表。
5. 独立枚举向量，包括孤儿。专用旧 vector queues 在归属确认后处理；混用 main queue/DLQ 按任务类型处理，禁止 purge。无法立即清除副本时报告最迟 TTL/retention 截止，不提前声明物理清零。
6. 验证旧任务/旧问答不能复活或发言、业务数据 key/count/hash 不变。日志七天、PITR 保留、DLQ 和备份分别登记副本消退证据。恢复旧备份后 memory 默认关闭，禁止自动导回。
7. dev 合成验收后单群设新 epoch/started_at；至少七天且实际样本门槛满足后推广其余白名单群。失败回到无长期记忆 ask，不能重新开启旧 memory。
8. 首版验收删除旧并行 profile/extractor/retrieval 路径。语义检索只能后续独立对照实验立项，不属于 V1。

Z18 云旧资源仅交付清单/手册；原授权是只读，不能据此删除旧 stack、SSM 或共享资源。Memory 清零必须满足上述依赖与精确范围，不是直接删表。

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
- 自动社交输出为 0；明确问答、captcha、反垃圾、抽奖、news/quiz 相关回归满足契约。
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
