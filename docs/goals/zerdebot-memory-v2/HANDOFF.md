# 下一次执行入口

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

历史独立 PR 在 TASKS 中，对应源码已通过最终集成#204合并。不要再依次合入旧分支。接下来的审阅对象是#205–#207；#208、#209已合并并完成本轮三个生产代码包读回与三次实际验证，不能将这次发布等同其余PR已上线。

以下依赖 anchor 仅解释历史审阅 diff：`feat/zerde-reviewed-foundation` → `feat/zerde-memory-v2-foundation` → `feat/zerde-memory-v2-answer-foundation`。它们包含多个当时的模块快照，现在不再作为待合入发布分支。后续发布仍须重新记录 SHA 和真实产物 hash。

用户后续授权已覆盖本轮具体发布、必要测试与原计划的旧记忆清零；不能继续套用合并前的只读限制。保持精确清单、停写、备份及条件删除边界。Z18非记忆旧云资源销毁仍单独列范围，不借本轮测试扩大删除。

现有`.github/workflows/deploy.yml`合并main自动部署dev，prod手动。本次为三个prod包的代码更新，未执行完整CDK部署；deploy workflow短暂暂停后已恢复active，分支保护规则不变。CloudFormation仍保留旧Code指针；#205配置修复合并并与当前现场环境同步前，不得直接运行完整CDK部署，以免覆盖实际代码和环境。两环境首次V2计费起点仍为1789134091，不得重置；旧表/index写入Deny围栏不变。

诊断续跑沿用原manifest和原绝对截止，六轮完成后已退出；9月12日16:20 UTC独立终检当时确认无操作进程/锁、原运行版本/环境/写入围栏不变、四个精确CONTROL键强读缺行，学习保持默认STOPPED。不要重新启动已完成的controller或重复终检。原启动与中断记录保留在[诊断阶段证据](evidence/2026-09-12-post-merge/cleanup-diagnostic-continuation.json)和现场时间线中。

终检后，root已于 **16:23:16 UTC**将原本地任务`zerde`恢复为原每日备份到期职责，完整字段实际读回匹配且ACTIVE。三份加密归档仍存在，原manifest/backup字节未变，独立密钥未删；到期清理尚未执行。原归档在 **9月18日16:49:52 UTC**到期，不延长；旧表实际PITR窗口为35天，保守复查点为 **10月17日16:20:38 UTC**，这只是后续复查时间，不是物理删除承诺。日志、队列和其他副本分别跟踪；到期清理依赖本机及Codex运行。Z18非记忆旧云资源未销毁，不能把保留的旧表和空索引当作资源已删除。

## 下一阶段仍需完成的真实证据

1. **完成其余PR审阅和配置同步。** #208/#209本轮已取得1,765项全量测试、all-files hooks、六个ARM包导入探针、两个CI检查及独立审阅通过；实际三包读回通过。#205–#207仍开放，完整CDK发布前须先处理前述配置与Code指针差异。后续源码另行固定测试和产物指纹，不复用本轮结果冒充验证。
2. **冻结配置并先保持学习 STOPPED。** 两环境成本计费起点相同，覆盖首次 V2 专属资源部署；不能用之后启用学习的日期掩盖早期费用。原始内容保留30天；dev 默认不消费；队列、超时、IAM、日志、告警接收人和共享预算表要读回。缺控制/计费许可时默认不学习。
3. **完成真实模型与评估证据。** 先独立复核合成 gold 的语言及事实标签，再使用实际 Gemini 输入/usage/输出形成独立 observations。固定 fixture 的分数不是模型效果。不得复制 gold、以全拒答满足来源100%，或因超时/预算暂停跳过样本后宣称完整覆盖。known 问题完整回答召回每语言至少90%，是防止原召回目标被空答绕过的测量补齐。
4. **dev canary。** 验证 Telegram 成员/管理员权限、每条来源链接、真实预算通知、Logs Insights 查询和用量归因，以及验证码、反垃圾、投票、News、Quiz 和显式媒体。恢复路径在真实依赖故障下的结果与合成测试分开记录。
5. **完成保留副本的后续验收。** 在线清零已独立通过，不再重跑本次删除或重新plan/backup。保留原manifest `67c71ec9bd6e62b43fd519a8b427f286dd81661a415f356912703db27f26e8f4`、执行与终检证据，按原9月18日到期职责处理本地密文和独立密钥；PITR在10月17日保守时间点之后实际复查，不能提前宣称物理清除。日志/DLQ/PITR/备份分别验收，3条设置所在表和空向量索引继续保留。Z10、Z19工单及整体验收不因此自动关闭；Z18其他资源仍需独立明确范围。
6. **单群启用与推广。** 先补齐清理后的旧任务回放，证明删除后不会恢复旧数据；清理前18条回放通过不能替代该项，本次只读终检也没有Invoke。前述门槛通过后，只为获准的试点群建立新学习 epoch。收集至少七天、50个有依据回答和20个未知问题，逐语言统计质量、零容忍、延迟和覆盖。样本不足继续保留 Z11 开放；达标后再推广并退役旧并行实现。

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

预算暂停仍保留短期来源准入、恢复与控制，因此仍有 AWS 消耗。$7模型预留是调用前控制；$3AWS是保守估算与停止可选工作的目标，不是账号账单硬封顶。按月使用/credits/税/净计费和项目归属证据分别记录。

## 本地重现入口

在完整集成分支运行：

```text
uv sync --frozen --python 3.13.6
uv run --frozen --python 3.13.6 pytest -q tests
uv run --frozen --python 3.13.6 pre-commit run --all-files
```

真实打包、离线回放及清理工具命令分别见 `scripts/verify_lambda_bundles.py`、`docs/MEMORY_V2_EVALUATION.md`、`docs/legacy-memory-cleanup.md`。不要运行旧历史导入。离线回放报告应保留 provider 类型、源码/fixture hash 和失败分项；数值 FAIL 的退出码2不能误报为执行崩溃或“测试通过”。
