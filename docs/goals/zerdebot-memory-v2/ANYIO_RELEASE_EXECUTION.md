# Z04 AnyIO 安全依赖发布（2026-09-27）

Goal：先修复现役包中的 AnyIO 安全告警，再继续 Z20 旧源码/资源清理。
Plan path：[FINISH_EXECUTION](FINISH_EXECUTION.md) 的 R2/R3 发布前置及 Z04。
Intent：保留现役网络调用、失败重试、超时取消与预算语义，消除已知依赖漏洞。
Truth owner：根 pyproject.toml/uv.lock；各 requirements 只由既有 exporter 生成。
Contract boundary：定向升级 AnyIO 至稳定版 4.15.1，最低修复约束 >=4.14.2,<5。
该版本在 Python <3.15 必需 typing-extensions>=4.16.0，因此同时升级这一个依赖；
它也用于 CDK，infra requirements 必须同步，Operations/common 包不受影响。
Cutover：独审与 CI 通过后，对 dev 再 prod 的已审阅 changeset 发布；核验每环境
Bot、Vector indexer、Memory worker、News、Quiz 的实际包版本，并保护第六个 Operations
及共享 layer。没有源变更的 layer 必须保持；不能套用 PR220“只更新三个核心函数”的断言。
Displaced path：旧 AnyIO 4.12.1 的五个受影响函数包；本 PR 尚不删除旧记忆源码或云资源。
Acceptance evidence：全量回归含 HTTP/DNS/TLS 主机名、取消超时、失败恢复与真实计量状态；
导出无漂移；六个 ARM Python3.13 handler probe；精确 changeset；实际 ZIP/layer/config
和控制/恢复保护读回。没有模型调用、Telegram 假聊天或新自然样本。
Kill criteria：非预期依赖/资源/config 变化、CONTROL/epoch 被改、预算责任被清除、
包版本缺失或其他验证失败即停止下一环境发布，记录实际部分状态。
Forbidden moves：开启新功能/新群/prod学习、重跑旧 once 发布脚本、删表、Receive/Purge
混合队列、重建历史账本或 UNKNOWN、重跑冻结模型/合成验收。

| Task | Owner | Input / files allowed | Files forbidden | Output / evidence | Depends on / parallel safe |
|---|---|---|---|---|---|
| A1 定向升级 | 主代理 | pyproject/uv.lock、5个导出、bundle probe及其契约测试 | 业务源码、冻结gold/scorer | 仅 AnyIO/必需typing依赖变化；导出与完整回归 | 已批准Z04；只读explorer可并行 |
| A2 审阅与集成 | 主代理＋独立reviewer/maintainer | A1 diff、计划/证据/工单 | 旧冻结报告 | POST、正确性与维护性审阅、CI、PR | A1；独审可并行 |
| A3 发布与读回 | 主代理＋独立verifier | 新目录的冻结候选、fresh live baseline及changeset | 旧once脚本/报告、业务数据 | dev/prod五包升级、六函数/层/配置保护读回 | A2；两个环境顺序发布 |
| A4 下一步 | 主代理 | Z20依赖图与删除清单 | 现役V2控制/预算 | 删除旧知识实现，再单独退休资源；同步全部状态 | A3；独立业务准备可并行 |

官方依据：[TLS 域名公告](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6)、
[进程池公告](https://github.com/agronholm/anyio/security/advisories/GHSA-5p39-cfhj-2xmp)。
两项首修版本均为4.14.2；升级不代表发现当前入口已遭利用。

## 实际 changeset 发现后的修订（尚未执行）

第一次五Code候选触及News/Quiz的ARN依赖，prod中文news rule及其permission明确在
changeset中。现场DISABLED但旧模板ENABLED，直接执行或回滚有恢复中文推送风险；
这两份未执行候选精确撤销，保留原构建/独审/CI及阻断证据，不当成已发布。

源码补充仅固定中文新闻规则`enabled=False`，其他语言和恢复任务保持；不新增配置入口。
先使用已验证旧模板仅修改该规则State一个leaf，独审其changeset（可能含完整对象未变的
permission ARN依赖），以DisableRollback=True校准CF声明与现有DISABLED状态。
这一步不更改任何Lambda Code，失败保留现场并前向修复，禁止恢复旧ENABLED模板。
UPDATE_COMPLETE及实际State/所有保护项读回后，重新捕获代码发布基线/LastUpdatedTime，
再建立五Code候选。此后代码发布可正常回滚到已DISABLED基线。新source须重新通过CI/独审。

五Code changeset另含唯一Bot DefaultPolicy的`PolicyDocument ← QuizLambda.Arn`
动态依赖；该完整模板对象不变、函数无替换且ARN固定。仅允许这一精确原因，并须
执行前后GetRolePolicy对同RoleName/PolicyName完整policy document等值；不泛化放行IAM。
新发布操作者/候选/changeset的审阅与实际读回均在新私有目录保存，旧once脚本不重跑。
