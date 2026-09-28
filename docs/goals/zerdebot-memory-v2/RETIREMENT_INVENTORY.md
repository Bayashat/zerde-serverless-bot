> 2026-09-28最终在线退役：[证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)；[执行与边界](LEGACY_STATS_FINAL_EXECUTION.md)；[副本台账](RETAINED_COPIES.md)。旧清理once全部结束，不重跑；运行源仍为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。

# 删除清单与执行状态（2026-09-28）

PR226已合并为`f3f77bc28fd80948fcfd11e6cc18d1980c6b93db`；运行构建源码为`01bdc1da2c5d995759eda0dfef99f7b427301d60`。两环境各14项、共28项本批旧资源已逐项确认不存在，prod的6个Retain对象也已另行物理删除并独审。两环境各五函数、层、配置、六张现役表和原控制/预算保护通过主检与独审，workflow ACTIVE。 [本轮实际资源退役证据](evidence/2026-09-27-retirement/resource-release.safe.json)。2026-09-28最后一批旧stats表与两个旧SSM路径已删除并独立确认不存在；临时恢复表也已删除。1条缺失历史统计按条件保全，3条已有统计不重复相加，8条旧实例投票不迁入且不声称过期。原28项、随后6项及本批3项合计37个已声明旧对象在线退役，6张现役表继续保留。Z20的源码与已声明在线资源范围完成；备份责任留Z10，业务与自然验收未完成，不新增启用。

本清单执行 [FINISH_EXECUTION](FINISH_EXECUTION.md) 的R2。`计划删除`不是`已删除`；补充字段核验确认3条旧SETTINGS没有自定义style，无需迁移有效业务设置；本批最终不存在证明见上方新证据。此清单所有已执行对象不重跑；未来发现的新对象必须另行核验和先告知，不能复用已结束的删除许可。区域均为`eu-central-1`，不以名称通配符删除。

## 已合并并部署删除的旧代码

9月27日已按事先告知清单移除下列13个旧算法模块及现役调用。PR224已合并并部署dev/prod，实际包及缓存缺失由双环境独立读回确认；本批专属云资源已由PR226部署及物理退役，最后旧stats及两旧SSM现也已独审退役。

| 对象 | 当前状态 / 处理 |
|---|---|
| `src/bot/services/group_memory.py`、`group_memory_processor.py`、`memory_extractor.py`、`memory_retrieval.py`、`vector_memory.py` | 已部署删除，实际包和缓存缺失已核验 |
| `src/bot/services/ambient_reactions.py`、`ai/proactive_decision.py`、`ai/ambient_reaction_prompt.py`、`ai/ambient_reaction_classifier.py`、`ai/channel_post_comment.py` | 已部署删除实现及仅为其服务的调用、测试、runtime配置；专属infra配置已在PR226退役 |
| `src/bot/services/repositories/group_memory.py`、`repositories/vector_memory.py` | 已部署删除；纯style normalizer已迁出，V2临时相册facade不再继承旧库，取消旧设置读取前和删表前两次fresh核验均已完成 |
| `src/bot/services/group_agent.py`内旧主动/频道分支 | 已部署删除退役分支；显式/ask、mention、reply和有效provider fallback保留 |
| `src/bot/services/history_import.py`及历史导入CLI旧写入实现 | 已部署删除算法，CLI所有参数在读文件或连接前立即说明退役并退出；审计证据保留 |
| vector-indexer入口和`infra/components/vector_indexer.py`等专属资源接线 | 专用入口、薄壳、CDK接线及打包目标已随PR226移除；混合主队列的小型旧任务拒绝协议仍保留 |

保留`memory_cutover`及router里的小型旧任务拒绝协议，防止混合主队列中的历史载荷恢复旧行为；它不是旧知识算法或可启用功能。删除它需另证所有入口不可能接受旧schema，不能为了“零关键词”移除安全边界。新V2、显式问答、临时媒体、验证码、反垃圾、投票、新闻、Quiz继续保留。

## 已实际退役：本批栈内资源（原删除前置保留供审计）

| 类型 | dev 精确名称 | prod 精确名称 | 删除前置 |
|---|---|---|---|
| DynamoDB旧记忆表 | `zerde-serverless-bot-memory-dev` | `zerde-serverless-bot-memory-prod` | 本次精确计数0/3；3条均只有旧开关和更新时间，无style_profile。取消旧读取的代码部署前及删表前均重验整行hash/字段白名单，期间保持停写保护；有变化即停，再保护有效语义；解除读取/env/IAM后删 |
| Lambda | `zerde-serverless-vector-indexer-dev` | `zerde-serverless-vector-indexer-prod` | 无生产者，旧在途退出，专属映射/权限退役 |
| 向量主队列 | `zerde-serverless-vector-memory-tasks-queue-dev` | `zerde-serverless-vector-memory-tasks-queue-prod` | 归属确认，visible/inflight/delayed均0；不用Receive/Purge证明空 |
| 向量DLQ | `zerde-serverless-vector-memory-tasks-dlq-dev` | `zerde-serverless-vector-memory-tasks-dlq-prod` | 上游退役、无其他redrive引用、数量核对 |
| S3 Vectors bucket | `zerde-serverless-memory-vectors-dev` | `zerde-serverless-memory-vectors-prod` | 独立枚举索引，确认没有别的用途 |
| S3 Vectors index | `zerde-serverless-group-memory-dev` | `zerde-serverless-group-memory-prod` | 刷新完整空索引证据；历史8259删除不是当前manifest |
| 日志组 | `/aws/lambda/zerde-serverless-vector-indexer-dev` | `/aws/lambda/zerde-serverless-vector-indexer-prod` | 函数退役、保留/审计职责单列后精确处理 |

对应栈为`zerde-serverless-telegram-bot-dev/prod`，**栈本身保留**。原dev Delete由CFN删除；原prod六个Retain对象已在脱管后另行删除，最终主检和独审逐项确认不存在。以上7种命名对象及各环境role/policy/mapping/4专属alarm合计14项，两环境28项；表中前置是已执行的审计契约，不是待重跑清单。

## 2026-09-28已实际退役：更早的六项空资源

- `zerde-prod-updates-queue`、`zerde-prod-updates-dlq`。
- `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-VOs3WfeNiAH7`。
- `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-Vz797oVzECIN`。
- `/aws/lambda/tg-dev-receiver`、`/aws/lambda/tg-dev-worker`。

精确依赖/空状态、两队列停写传播与稳定空窗、逐项删除及独立不存在读回均已完成。原S4的28项加本批6项共34项已退役对象；不代表账号只剩现役资源。没有新增备份，历史日志导出/外部副本未穷尽，不能宣称所有副本消失。恢复同名资源只恢复定义，不恢复内容。

## 最后一批已实际退役

`zerde-prod-bot-stats`、`/zerde/bot/token`、`/zerde/bot/webhook_secret`已删除并独审不存在；恢复临时表已删除。1条统计条件保全、3条原值覆盖、8条旧投票不迁入。37＝原S4 28＋六空资源6＋本批3；临时恢复表不计入旧对象。精确分类AV已按提前完成条款移除并独审。

两旧SSM是完成有限已知消费者核查后退役，CloudTrail批量读取未穷尽的限制保留；参数路径删除不等于底层凭据撤销。没有读取/复制/轮换现役或旧参数值。[执行与独立证据](LEGACY_STATS_FINAL_EXECUTION.md)。已声明旧源码和在线候选无待删项；副本与未声明未知资源不冒称全部消失。

副本独立跟踪：旧stats USER备份于2026-10-05 08:18:35.953 UTC执行精确删除与不存在核验；原PITR于2026-10-17 16:20:38 UTC复查；旧memory SYSTEM服务到期2026-11-01 11:46:02.425 UTC；本批stats SYSTEM服务到期2026-11-02 08:45:11.254 UTC，均须按原身份到期读回。原Oct4临时AV已按本批提前完成条件移除并独审；文件移除不是安全抹盘。

## 明确保留的6张现役表（不是账号表总数）

| 名称 | 用途 |
|---|---|
| `zerde-serverless-bot-stats-dev` / `zerde-serverless-bot-stats-prod` | 统计、验证码、投票、反垃圾、operations等业务；未迁入死开关；prod仅条件保全1条旧审核统计 |
| `zerde-serverless-quiz-dev` / `zerde-serverless-quiz-prod` | Quiz发布、poll、答案和计分 |
| `zerde-serverless-memory-v2-dev` / `zerde-serverless-memory-v2-prod` | V2事实、控制、来源、恢复与预算；prod还承接项目共享费用账本，非空不表示已开生产学习 |

现役Bot/News/Quiz/Operations/V2 worker、API、混合主队列及DLQ、V2/operations队列、必要告警/日志、共享Layer/CDK assets、其他项目均保留。两个旧SSM路径已按本批范围删除；四个现役Bot/Webhook参数投影保持，值未读取或轮换。

现有dev学习控制和epoch保持，只读校验，不把revision24写成强制恢复值；prod不新增CONTROL。budget/UNKNOWN/费用历史、失败恢复记录保留。PITR与其他副本职责归Z10；不要把源表不存在说成所有副本物理消失。

## 验收与恢复

Z10原PITR复查仍为2026-10-17 16:20:38 UTC；S4旧memory SYSTEM的实际服务到期为2026-11-01 11:46:02.425 UTC，本批旧stats SYSTEM为2026-11-02 08:45:11.254 UTC。这是复查/服务到期信息，不是已物理抹盘证明；日志/DLQ/其他副本职责继续，已移除本地密文/key不重建。

每个删除项登记旧资源身份、所有权、依赖解除、操作时间、结果和独立不存在读回；对6张保护表及settings、控制/预算做前后校验。失败保留实际部分状态，禁止重复跑已完成的once清理；新事实系统失败只退无长期记忆ask。必要settings备份只包含这次迁移的业务数据，设置负责人和到期日，不重建过期的旧聊天归档。删表恢复不自动还原stream、TTL、PITR、IAM，必须单独验证；队列/日志不承诺可恢复内容。

历史起点证据（不作当前删除门禁）：原只读表盘点SHA256 `5106db4ad4efb6feb7f985377d7fe2f95139d1d7bf4515048ee1317b53e21d8d`；候选依赖说明SHA256 `edd2f46b3cf3cea7b8049ce7019fee3503825806c7df614bb028a06a874a6cfa`。后者的向量资源身份来自9月23日冻结模板/读回，孤儿队列日志仍为9月10日证据；执行前必须刷新，不能冒充当前全资源检查。
