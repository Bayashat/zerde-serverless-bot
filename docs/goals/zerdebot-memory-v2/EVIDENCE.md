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
