# 删除前清单（2026-09-26；均未在本轮删除）

本清单执行 [FINISH_EXECUTION](FINISH_EXECUTION.md) 的R2。`计划删除`不是`已删除`；补充字段核验确认3条旧SETTINGS没有自定义style，当前无需迁移有效业务设置；这不是删完的证明。正式操作前必须刷新精确身份、消费者、数据/保护项校验和changeset，并先向用户告知。区域均为`eu-central-1`，不以名称通配符删除。

## 准备删除的代码

| 对象 | 当前状态 / 处理 |
|---|---|
| `src/bot/services/group_memory.py`、`group_memory_processor.py`、`memory_extractor.py`、`memory_retrieval.py`、`vector_memory.py` | 旧记忆算法仍在仓库/打包范围，入口退休；拆除所有现役import后删除 |
| `src/bot/services/ambient_reactions.py`、`ai/proactive_decision.py`、`ai/ambient_reaction_prompt.py`、`ai/ambient_reaction_classifier.py`、`ai/channel_post_comment.py` | 自动互动已停；删除实现、仅支持这些能力的配置/测试/依赖 |
| `src/bot/services/repositories/group_memory.py`、`repositories/vector_memory.py` | 旧巨型仓库仍通过继承承接settings；保留纯style normalizer，取消已无有效自定义设置的读取，并解耦V2临时相册后删 |
| `src/bot/services/group_agent.py`内旧主动/频道分支 | 只删退役分支；显式/ask、mention、reply和有效provider fallback保留，不整文件误删 |
| `src/bot/services/history_import.py`及历史导入CLI旧写入实现 | 不再提供可运行导入器；已完成清理的审计证据与必要离线恢复记录保留 |
| vector-indexer入口和`infra/components/vector_indexer.py`等专属资源接线 | 先撤所有生产者；代码过渡期仅拒绝旧任务，云资源移除后删薄壳及专属打包目标 |

保留`memory_cutover`及router里的小型旧任务拒绝协议，防止混合主队列中的历史载荷恢复旧行为；它不是旧知识算法或可启用功能。删除它需另证所有入口不可能接受旧schema，不能为了“零关键词”移除安全边界。新V2、显式问答、临时媒体、验证码、反垃圾、投票、新闻、Quiz继续保留。

## 核验后删除：当前栈内退役资源

| 类型 | dev 精确名称 | prod 精确名称 | 删除前置 |
|---|---|---|---|
| DynamoDB旧记忆表 | `zerde-serverless-bot-memory-dev` | `zerde-serverless-bot-memory-prod` | 本次精确计数0/3；3条均只有旧开关和更新时间，无style_profile。取消旧读取的代码部署前及删表前均重验整行hash/字段白名单，期间保持停写保护；有变化即停，再保护有效语义；解除读取/env/IAM后删 |
| Lambda | `zerde-serverless-vector-indexer-dev` | `zerde-serverless-vector-indexer-prod` | 无生产者，旧在途退出，专属映射/权限退役 |
| 向量主队列 | `zerde-serverless-vector-memory-tasks-queue-dev` | `zerde-serverless-vector-memory-tasks-queue-prod` | 归属确认，visible/inflight/delayed均0；不用Receive/Purge证明空 |
| 向量DLQ | `zerde-serverless-vector-memory-tasks-dlq-dev` | `zerde-serverless-vector-memory-tasks-dlq-prod` | 上游退役、无其他redrive引用、数量核对 |
| S3 Vectors bucket | `zerde-serverless-memory-vectors-dev` | `zerde-serverless-memory-vectors-prod` | 独立枚举索引，确认没有别的用途 |
| S3 Vectors index | `zerde-serverless-group-memory-dev` | `zerde-serverless-group-memory-prod` | 刷新完整空索引证据；历史8259删除不是当前manifest |
| 日志组 | `/aws/lambda/zerde-serverless-vector-indexer-dev` | `/aws/lambda/zerde-serverless-vector-indexer-prod` | 函数退役、保留/审计职责单列后精确处理 |

对应栈为`zerde-serverless-telegram-bot-dev/prod`，**栈本身不删除**。当前模板dev存储Delete，prod Retain；CDK移除不等于prod物理删除，操作回执必须区分。

## 待核实，尚不进入执行删除名单

- `zerde-prod-bot-stats`：更早旧表，约12行；不在当前栈、12个现役函数TABLE环境变量无引用。仍需核实外部脚本、别名/旧版本、stream等消费者，保护设置、恢复方案和真实内容范围；现在不能直接删。
- `zerde-prod-updates-queue`、`zerde-prod-updates-dlq`：9月10日旧候选；刷新存在性、生产/消费/redrive引用及空队列证据。
- `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-VOs3WfeNiAH7`
- `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-Vz797oVzECIN`
- `/aws/lambda/tg-dev-receiver`
- `/aws/lambda/tg-dev-worker`

以上4个日志组须刷新函数不存在、无subscription、存储/最后事件及保留需求；出现新活动则阻止空孤儿路径。恢复同名队列/日志不能恢复其内容。

## 明确保留的6张现役表

| 名称 | 用途 |
|---|---|
| `zerde-serverless-bot-stats-dev` / `zerde-serverless-bot-stats-prod` | 统计、验证码、投票、反垃圾、operations等业务；本次无有效自定义设置需要迁入，不新增死开关记录 |
| `zerde-serverless-quiz-dev` / `zerde-serverless-quiz-prod` | Quiz发布、poll、答案和计分 |
| `zerde-serverless-memory-v2-dev` / `zerde-serverless-memory-v2-prod` | V2事实、控制、来源、恢复与预算；prod还承接项目共享费用账本，非空不表示已开生产学习 |

现役Bot/News/Quiz/Operations/V2 worker、API、混合主队列及DLQ、V2/operations队列、必要告警/日志、共享Layer/CDK assets、其他项目均保留。`/zerde/bot/token`和`/zerde/bot/webhook_secret`外部消费者不明，本清理范围不删；现役SSM密钥不变。

现有dev学习控制和epoch保持，只读校验，不把revision24写成强制恢复值；prod不新增CONTROL。budget/UNKNOWN/费用历史、失败恢复记录保留。PITR与其他副本职责归Z10；不要把源表不存在说成所有副本物理消失。

## 验收与恢复

每个删除项登记旧资源身份、所有权、依赖解除、操作时间、结果和独立不存在读回；对6张保护表及settings、控制/预算做前后校验。失败保留实际部分状态，禁止重复跑已完成的once清理；新事实系统失败只退无长期记忆ask。必要settings备份只包含这次迁移的业务数据，设置负责人和到期日，不重建过期的旧聊天归档。删表恢复不自动还原stream、TTL、PITR、IAM，必须单独验证；队列/日志不承诺可恢复内容。

证据：本次只读表盘点SHA256 `5106db4ad4efb6feb7f985377d7fe2f95139d1d7bf4515048ee1317b53e21d8d`；候选依赖说明SHA256 `edd2f46b3cf3cea7b8049ce7019fee3503825806c7df614bb028a06a874a6cfa`。后者的向量资源身份来自9月23日冻结模板/读回，孤儿队列日志仍为9月10日证据；执行前必须刷新，不能冒充当前全资源检查。
