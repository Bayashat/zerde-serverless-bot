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
