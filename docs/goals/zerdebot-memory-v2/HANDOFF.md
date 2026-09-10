# 下一次执行入口

当前阶段是 **PR_OPEN / IMPLEMENTED_UNPROVEN**。已创建 Epic #157、Z01–Z19 工单及独立实现 PR；完整代码在 `feat/zerde-complete-integration`，计划与证据在 `feat/memory-v2-execution-plan`。不要从旧 `main` 重做这些实现，也不要把依赖 anchor 分支当作已部署版本。

[最终集成 PR #204](https://github.com/Bayashat/zerde-serverless-bot/pull/204) 面向 main；[评估领域回放 #203](https://github.com/Bayashat/zerde-serverless-bot/pull/203) 和 [Memory 公共入口 #202](https://github.com/Bayashat/zerde-serverless-bot/pull/202) 均已包含其中。审阅应检查最终组合与各独立变更。

先读取 [PLAN](PLAN.md)、[TASKS](TASKS.md)、[EVIDENCE](EVIDENCE.md)，再检查 GitHub 当前 PR head、审阅及部署状态。本文记录交接时的事实；后续执行以新的实际读回为准。

## 已有实现

- Z01–Z04：自动互动停用、旧记忆隔离、日志脱敏、删除白名单、可复现打包和依赖安全升级。
- Z05–Z09：独立表、唯一事实 writer、可靠消息摄取/恢复、结构化抽取、当前有效事实档案、有来源问答、群话题样本、更正/遗忘/退出、编辑失效与发送前复验。
- Z10：精确 manifest、加密备份、白名单清理、业务记录保护及旧任务回放工具。未运行生产 plan/backup/apply。
- Z11：四语言合成语料、独立评分器和真实领域代码离线回放。固定假 provider 只测试工程链路；不能当作 Gemini 质量证据。
- Z12–Z16、Z19：验证码、反垃圾、Voteban、News、Quiz、抽奖 SDK 边界修复，已在共享入口组合验证。
- Z17–Z18：告警/恢复通知、dev 按需开关、模型预留、AWS 计量/监控和旧资源清理手册。成本标签、真实通知和云资源删除均未执行。

## 审阅与合入

每项变更的独立 PR 在 TASKS 中。最终集成 PR 用于检查完整源码与共同入口，不代替各模块审阅。合入应保留最终集成的语义修复；单独依次合早期 PR 后，不能漏掉 #192、#197、#198–#202 和后续评估/集成补丁。

依赖 anchor 用于固定审阅 diff：`feat/zerde-reviewed-foundation` → `feat/zerde-memory-v2-foundation` → `feat/zerde-memory-v2-answer-foundation`。它们包含多个已审阅模块，不能在未审阅各 PR 的情况下作为捷径合入。最终发布提交需重新记录 SHA 和真实产物 hash。

当前没有合并、部署、真实模型调用、Telegram 发信或生产数据写入。原 AWS 授权为只读；实际云变更和清零须按已审阅的具体发布/删除范围执行，Z18 的旧云资源删除单独授权。

## 上线之前需要的真实证据

1. **通过 GitHub 审阅及当前 CI。** 将最终集成修订与发布锁文件固定。打包必须使用实际 CDK 资产和 ARM64 Lambda 导入，不能仅凭 mocked construct 测试。
2. **冻结配置并先保持学习 STOPPED。** 两环境成本计费起点相同，覆盖首次 V2 专属资源部署；不能用之后启用学习的日期掩盖早期费用。原始内容保留30天；dev 默认不消费；队列、超时、IAM、日志、告警接收人和共享预算表要读回。缺控制/计费许可时默认不学习。
3. **完成真实模型与评估证据。** 先独立复核合成 gold 的语言及事实标签，再使用实际 Gemini 输入/usage/输出形成独立 observations。固定 fixture 的分数不是模型效果。不得复制 gold、以全拒答满足来源100%，或因超时/预算暂停跳过样本后宣称完整覆盖。known 问题完整回答召回每语言至少90%，是防止原召回目标被空答绕过的测量补齐。
4. **dev canary。** 验证 Telegram 成员/管理员权限、每条来源链接、真实预算通知、Logs Insights 查询和用量归因，以及验证码、反垃圾、投票、抽奖、News、Quiz 和显式媒体。恢复路径在真实依赖故障下的结果与合成测试分开记录。
5. **停旧写入、排空并清零。** 使用最终源码的 `docs/MEMORY_CUTOVER.md` 和 `docs/legacy-memory-cleanup.md`。Bot/indexer/aliases/旧 schedule/外部导入全纳入停写清单；排空实际旧 timeout 最大值加60秒，审计旧 indexer 为900秒。随后按同一个干净提交生成 manifest、备份与 apply；禁止整表删、混合队列 purge、把 V2 表或预算/业务表填入 scope。在线清理与日志/DLQ/PITR/备份副本分别验收。
6. **单群启用与推广。** 前述门槛通过后，只为获准的试点群建立新学习 epoch。收集至少七天、50个有依据回答和20个未知问题，逐语言统计质量、零容忍、延迟和覆盖。样本不足继续保留 Z11 开放；达标后再推广并退役旧并行实现。

真实 provider 评估与 dev 验证可在清零生产前完成；生产单群学习必须晚于该群旧数据清零、控制与部署核验。AWS 成本起点和群学习时间是两个独立边界。

## 配置读回清单

- `MEMORY_COST_METERING_STARTED_AT`：唯一新增手填计费起点，dev/prod相同。CDK注入的表/队列/共享费用账本/topic/schema/解析后inventory hash不另建同名人工配置来源。
- `DEV_RUNTIME_ENABLED=false`：默认关闭六个Lambda执行、三条SQS映射和恢复调度；dev canary需明确启用并核对积压及Telegram环境隔离。启停不会自动改变群学习控制记录。
- `ADMIN_USER_ID`：当前单一私聊接收人，正整数，需先私聊bot。核对SSM权限；News/Quiz专用群配置为空时会回退共享 `CHATS_*`，不能误发到生产群。
- Memory worker120秒、并发2、队列可见740秒；日志七天；prod Quiz与V2表PITR七天，dev关闭。恢复演练用新表验证，不能覆盖现表。实际Lambda环境变量必须低于4KiB。
- 活跃环境各22个告警，dev停用为0；两个环境都启用则44。成本inventory的10仅是两环境新增Memory告警预留，不是总告警数。需实测告警、恢复及通知失败路径到管理员。
- 真实成本门槛包括实际Logs Insights语法、START/Final/REPORT关联、零与非零样本、完整时间范围及暂停恢复。项目成本标签尚未激活；账号费用仍不能直接当Zerde独立实付金额。

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
