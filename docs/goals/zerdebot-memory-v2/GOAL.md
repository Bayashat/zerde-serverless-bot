# Goal: ZerdeBot Memory V2 与可靠性修复

使用 Krypton Execution 执行同目录 [PLAN.md](PLAN.md)，由 [TASKS.md](TASKS.md) 选择依赖已满足的未完成工单。开始前读取 [EVIDENCE.md](EVIDENCE.md) 及对应 issue，检查当前分支/PR/部署，避免重复创建或覆盖正在执行的工作。

本次代码交付后的继续执行步骤见 [HANDOFF.md](HANDOFF.md)。完整实现位于 `feat/zerde-complete-integration`；PR_OPEN 不等于生产验收完成。

- PLAN 是已批准契约；GitHub Epic/子工单镜像执行进度。
- 坚持唯一事实 writer、独立 V2 表、epoch/revision、明确自述、跨群隔离、可更正/遗忘、来源支持。
- 旧 memory 与自动社交不得成为 fallback；无记忆 ask 是安全回退。
- 不把 code/PR/部署成功当真实产品验收，不足时标记 IMPLEMENTED_UNPROVEN。
- 初版按任务独立 PR；用户追加的 Z19 抽奖退役直接进入 #204。记录本地、构建、部署读回、canary、真实样本的证据。
- 保护 settings、验证码、统计及其他保留业务数据；已退役抽奖记录仅按明确root scope清理；清零必须精确 manifest、备份、旧任务隔离和回读核验，禁止整表删除/混合队列 purge。
- Z18 只交付旧云资源清单和手册，旧云资源删除需要另有具体授权。
- 不在 GitHub、日志或报告里提交聊天正文、个人标识、token、secret 或原始模型上下文。
- 不重新执行已经记录完成的 audit 全表扫描/跨区枚举，只有状态可能变化且当前任务需要时才刷新。
