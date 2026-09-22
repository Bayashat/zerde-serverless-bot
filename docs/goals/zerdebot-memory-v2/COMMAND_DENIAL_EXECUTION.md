# #219 明确个人记忆权限拒绝

Goal / Intent：他人尝试更正、标错个人事实，或遗忘明确属于他人的来源时，收到准确的权限提示；确定的拒绝不无限保留为未完成命令。
Plan path：[已批准PLAN](PLAN.md)，[Z09](https://github.com/Bayashat/zerde-serverless-bot/issues/166)后续[问题#219](https://github.com/Bayashat/zerde-serverless-bot/issues/219)。
Truth owner：MemoryCommandService 决定主体/来源权限；CommandReceipt 是唯一投递身份、租约、终态与重投 owner；public_commands 只负责本地化展示。
Contract boundary：新增 MemoryOwnershipDenied 只表示可信目标属于另一人、且还没有业务修改。PENDING → DENIED 用原 scope 检查、租约和 revision CAS；重投返回同一拒绝，不再执行事实修改。APPLIED 和成功标错的 REJECTED 保持原语义。
Cutover / Displaced path：这些明确的主体权限拒绝不再走通用 unavailable 文案。现有群管理员预授权仍在收据建立前拒绝。旧 PENDING 不批量回填；已有来源删除恢复的非本人检查仍是 unavailable，不能把恢复中的不确定性扩展成新终态。
Acceptance evidence：真实SDK/Moto公开入口验证四语言、重复投递、提交前失败/提交成功丢响应、合法修改未知结果恢复、观察版本及租约失效；dev真实双身份验收另记，不能用本地测试代替。
Kill criteria：任何他人事实变化、历史任务重执行业务、未知结果变成确定拒绝、原范围/租约围栏减少，均禁止发布。
Forbidden moves：不改现有学习开关/epoch，不扩大群范围、不改基础设施、模型、费用、删除/恢复owner，不清历史收据。

| Task | Owner | Input / files allowed | Output / evidence | Depends on / parallel safe |
|---|---|---|---|---|
| 探索及PRE | code reviewer | 原PR218与#219、commands/receipts/public adapter | 最小权限边界及故障列表 | 独立只读，可与实现并行 |
| 实现与测试 | root | models.py、commands.py、command_receipts.py、public_commands.py、针对性测试与本文相关文档 | 明确拒绝/持久终态/保留未知恢复 | 原owner；不改云状态 |
| POST正确性与维护 | independent reviewers | 最终diff、相关测试 | 归属、安全、状态机与唯一owner审查 | 实现后 |
| 发布与真实验证 | root + independent verifier | 通过review/CI的固定source及当前配置 | 合并、dev/prod制品读回与原生客户端结果分别记录 | 本地通过后，沿现有发布授权 |

本地阶段：28项新增故障/公开入口测试通过；包含既有控制重投、领域权限、公开入口的82项组合独立复核通过；正确性及维护POST均ALIGNED，pre-commit通过。全量CI及真实部署/客户端验收单独记录，不能从本地结果推断上线。旧两个PENDING不自动回填。
