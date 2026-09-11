# Memory V2 预算计量与暂停

本模块是本地实现的预算保护，尚未经过线上计量、SNS 私聊或 AWS 账单对账验收。
`ESTIMATE_VERIFIED` 表示登记资源的观测与计量契约完整，不表示 AWS 已核实发票。
未部署、缺仪表、缺当月历史或缺权限时，新版可选学习和回答增强默认暂停。
原始数据到期、删除、状态恢复和普通显式问答由各自 owner 决定，不应被预算暂停误伤。

## 金额和唯一 owner

| 范围 | 全项目月预算 | 通知与停止条件 |
| --- | --- | --- |
| 模型 | USD 7 | 80% / 90% 可通知；下一次完整保守预留放不进 USD 7 才停止。不会在 USD 6.30 擅自停用。 |
| 新版记忆 AWS 估算 | USD 3 | 80% 通知；90% 起停止可选学习和增强，当月保持暂停。 |

dev/prod 共用 **prod Memory V2 表**里的 `MEMORY_BUDGET#*` / `MEMORY_ATTEMPT#*`
费用分区。dev 的事实、来源和个人资料仍在 dev 表。`MemoryBudgetRepository` 是
MODEL/CONTROL 和模型预留的唯一写入者；`CostState` 只写 AWS、扫描预留、计量块和通知。
监控只在 prod 每小时执行，通知中的环境表示发起环境，不是每个环境各有一份预算。

金额均为整数美元百万分之一。AWS 目录按 Frankfurt 公布的毛价，不扣 Free Tier、
账户 credits、退款或税，不把账户总费用当成项目费用。估计还包含部分整月预留，
所以也不是“截至目前已发生的净账单”。模型金额由原有模型目录单独计算。
AWS 服务不会因此获得硬封顶：已有基础业务、停用后的固定资源、恢复和监控仍可计费。

## 默认估算范围

`CostInventory` 的闭合 schema 1 必须同时登记两环境的以下资源；遗漏 idle dev 或 DLQ
也会失败，而不是把缺项当零。region 目前只能是 `eu-central-1`。

- 两个 `zerde-serverless-memory-v2-worker-{env}`、两个 `zerde-serverless-bot-{env}`，
  使用精确 `/aws/lambda/{name}` 日志组。
- 两个 `zerde-serverless-memory-v2-{env}` 表及 `work-due` GSI；登记各表 PITR 状态。
- 两个 `zerde-serverless-memory-v2-queue-{env}` 和两个 `zerde-serverless-memory-v2-dlq-{env}`。
- 两个环境最多 10 个新增标准 CloudWatch 告警，每月按 USD 1.00 全额预留；dev 关闭时也不扣回。

专用 worker 按所有 REPORT 的完整 billed duration 和请求数计价。触及 V2 的共享 Bot
调用也按**整次** REPORT 计价，包含原有业务花费的时间；这是共享调用上估，不能描述成
纯记忆增量。未触及 V2 的既有 Bot 调用不纳入默认目录。旧 memory/vector、News、Quiz、
验证码、反垃圾等基础业务成本不在此新增资源口径内；清理及全账户账单是另外的审计范围。

专用表/GSI 按 CloudWatch 消耗单位计价。当前 storage 加上当月每个写单位的 1,124 bytes
按整月存储费预留，更新、删除和 GSI 会被重复高估。若有任一 PITR 表，将这一合计也按
PITR 整月计价。当前日志存量和新增日志另计存储；共享 Bot 每个 V2 调用还预留 64 KiB
新增日志。没有把日志扫描或监控自身默认算成免费。

队列以 sent / received / deleted / empty receive 指标计量；payload 按读回的最大消息长度
向上分成 64 KiB 单位，额外计每次 receive 两个控制操作，以及每队列每日 1,000 次控制
操作预留。它有意高估批处理和小消息，不是精确 SQS 发票。未知 API、超出契约的调用
需要补目录或使仪表 `complete=0`，不能悄悄填零。

## 价格来源与限制

目录版本为 `aws-eu-central-1-gross-2026-09-11`。以下是 2026-09-11 从公开区域 Price List
读取的第一收费档；即使账户可能有免费额度也使用毛价。

| 项 | USD 单价 |
| --- | --- |
| DynamoDB WRU / RRU | 0.0000007625 / 0.0000001525 |
| DynamoDB 标准 storage / PITR，GiB-month | 0.306 / 0.2448 |
| Lambda ARM GB-second / request | 0.0000133334 / 0.0000002 |
| SQS standard request unit | 0.0000004 |
| Logs standard ingest / store / Insights scan，GiB | 0.63 / 0.0324 每月 / 0.0063 |
| GetMetricData 每查询 metric / 标准 alarm-month | 0.00001 / 0.10 |
| SNS publish（Lambda 投递免费） | 0.0000005 |

公开原始价目：
[DynamoDB](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonDynamoDB/current/eu-central-1/index.json)、
[Lambda](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSLambda/current/eu-central-1/index.json)、
[CloudWatch](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudWatch/current/eu-central-1/index.json)、
[SQS](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSQueueService/current/eu-central-1/index.json)、
[SNS](https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonSNS/current/eu-central-1/index.json)。
这些 `current` URL 会更新；修改锁定目录必须重新记录日期和版本，并复核所有 handler 的契约。
[CloudWatch 价格说明](https://aws.amazon.com/cloudwatch/pricing/)解释 GetMetricData 的收费单位。

目录不支持 provisioned concurrency、SnapStart、额外临时磁盘、VPC/NAT、DynamoDB global
table/LSI/stream、额外 GSI、KMS 收费或 FIFO 队列；实际配置出现这些情况会 UNVERIFIED。
额外服务、数据传输和未知调用不能凭本目录宣称“全部 AWS 费用均已计入”。

### 标准队列元数据兼容修复（2026-09-11）

实际只读对照发现：对同一 V2 标准队列请求 `FifoQueue` 属性返回
`InvalidAttributeName`；仅移除它，保持 QueueArn、CreatedTimestamp、MaximumMessageSize、
KmsMasterKeyId 四个属性不变即成功，返回前三项，KmsMasterKeyId 缺失。
[SQS 官方接口](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_GetQueueAttributes.html)
将 FifoQueue 限定为 FIFO 队列，并说明可通过队列名的 `.fifo` 后缀识别类型。

读取器不再请求 FIFO 专属属性。标准类型仍由闭合 inventory 的规范名称、精确 URL 和返回 ARN
共同确认；不接受 `.fifo` 名称或矛盾的 FIFO 标志。创建时间、消息大小及 KMS 边界保持：
只有可选 KmsMasterKeyId 缺失沿用无 KMS 额外计费分支，不能据此称队列未加密；本次没有读取
SqsManagedSseEnabled。缺少其他必需字段、ARN 不匹配、异常大小、未覆盖的旧创建时间、KMS
或 SDK 错误仍记为 UNVERIFIED，禁止发出可选模型工作许可。

本地回归使用真实 botocore 请求序列化/响应解析、合成 HTTP 回包及 Moto 预算事务；这些测试
不调用 AWS，也不证明整套生产成本仪表已恢复。修复发布后须实际重新测量，并核验历史覆盖和
其余资源/REPORT 门槛，不能直接改账本状态或推进计费起点。

## 无正文仪表契约

Bot 和 memory-worker 在每次 invocation 的首次 V2 touch 发一次 Start；每个 V2 span
汇总到相同 request_id，finally 只发一次 Final。字段位于 JSON 日志最外层：

```json
{"cost_event":"MemoryV2CostStart","cost_schema":1,"request_id":"<context.aws_request_id>","memory_request":1}
{"cost_event":"MemoryV2Cost","cost_schema":1,"request_id":"<same id>","complete":1,"elapsed_ms":42,"shared_stats_rru":100,"shared_stats_wru":400,"shared_sqs_units":115}
```

这些是格式示例，不是实际用量。所有单位必须非负，elapsed_ms 向上取整，complete 只可为
0 或 1。没有聊天正文、prompt、user/chat ID、数据库 key、响应 body 或凭证。worker 也会
操作 shared stats 配额/CLEAN 收据，因此必须具有相同仪表。监控自身运行也应进入该 Bot
仪表，以便后续小时读回自身实际 billed duration；仅靠一个固定常数不能证明运行成本完整。

shared stats/main queue 由 runtime 显式 allowlist 识别；专用 V2 表/队列走 CloudWatch，
不要再加入共享单位。SDK 在每次真实 before-send 预记：单项读最多 400 KiB，Query/Scan
最多 1 MiB，事务双倍，batch 按已登记 shared items 的上限累加。写操作还保守预留失败
条件读取。只有成功且 ReturnConsumedCapacity 完整时可以退该 attempt 的差额；失败、
重试、缺 CC 都保留上界。未知 shape 或未成功安装完整 hook 必须 complete=0。

共享队列单次 send 预留 16 单位，再按每条消息最多 3 次 receive/delete/DLQ 上界预留
`3 × (16 + 1 + 16)`；实际再被捕获的消费者调用可能重复上估。该前提依赖 root 的
maxReceiveCount/最大消息尺寸接线；不能界定就保持不完整。仪表具体 SDK 捕获由 runtime
集成 slice 负责，本模块不会自行伪造 complete=1。

Logs Insights 固定查询先按日志组/request_id 关联，再逐 invocation 校验恰好一条
Start、Final、REPORT 及平台 START、schema、完整性和非负单位，最后只返回日志组级数字。
`invalid_records` 必须为 0；不能靠“A 多一个 Final，B 缺一个 Final”抵消总数。
无原始消息和 request_id 返回给监控。worker REPORT 总数还必须与 Lambda Invocations
指标相符；共享 Bot 只筛触及 V2 的调用。

不以 Lambda Duration 代替完整计费时间：[AWS 已将 INIT 纳入计费](https://aws.amazon.com/blogs/compute/aws-lambda-standardizes-billing-for-init-phase/)。
查询以 `@billedDuration × (@memorySize / 1000000 / 1024) / 1000` 得到 GB-second；
[官方查询示例](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-examples.html)
将自动发现的 memorySize 除以一百万换成配置 MB。
[官方函数文档](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-operations-functions.html)
定义了本查询使用的 coalesce、ispresent 和 if。

## 历史覆盖、缺项与扫描费用

`metering_started_at` 是经批准的首个 V2 部署时刻，不能在故障后推进来抹去历史。
专用资源创建早于该时刻 15 分钟以上会被拒绝；这是首次上线证据检查，不能替代实际
代码切换和旧 writer 排空验收。更改月中 inventory 要审阅重建，不能重置账本假装零。

UTC 当月按最长 12 小时块持久化覆盖，每次最多补一个块，优先补缺失历史。查询窗口
两侧各留 15 分钟关联跨边界调用，按平台 START/最早记录分配且 core 不重叠。
[Lambda 指标时间是 invocation 开始时间](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-view.html)，
因此不能按 REPORT 结束时间分桶：11:59 开始、12:00 完成的调用仍归入前一个块。
缺平台 START 会使逐 invocation 校验失败；不会丢弃该有 marker 的记录来制造完整结果。
只使用当前时刻至少 15 分钟之前、5 分钟对齐的数据。成功块的金额/写单位只增不减。
长停机后逐小时补历史；历史已超过任何相关日志保留期则无法证明完整，当月继续暂停，
不能把过期日志的 Complete 空结果补成零。迟到数据仍有观测延迟风险；此机制不是实时账单。

CloudWatch GetMetricData 最多 5 页，必须出现全部精确 query IDs，不能有 warning、PartialData、
冲突分页或越界点。按固定 namespace/dimensions 构建，读回资源名字/类型/日志/版本；不传
Unit，避免错误单位导致假空。[AWS API 语义](https://docs.aws.amazon.com/AmazonCloudWatch/latest/APIReference/API_GetMetricData.html)
中的 Complete 空点只表示没有**已报告**使用量。全新空闲资源需同时有精确存在证据、
正确仪表版本、从首次部署起完整时间覆盖和预留；不会因此获得“账单为零”的结论。

REPORT 查询每次最多 worker/Bot 两个，合计轮询期限 45 秒；具体 SDK 调用还受短超时限制。
失败/超时且 query ID 已知时 StopQuery；StartQuery 响应丢失且 ID 未知时无法定向取消，
因此不能声称本地期限会神奇终止服务端扫描，也不能重用该预留 ID 重新发起。
每查询前持久预留 64 MiB 扫描费用（约 394 micro-USD），同时撤销原 AWS permit。
已知日志存量超过此限拒绝扫描。完成后据 bytesScanned 结算；未知不退款，实际超额补记
并让当月 UNVERIFIED。64 MiB 是调用方的保守预留，**不是 AWS 的 server-side byte cap**。

估计额另外预留整月每小时 API 查询成本（当前调用数至少按 64 单位/小时），USD 0.10
迟到/未覆盖小额开销，USD 0.10 监控和通知运行 allowance。扫描另有独立实记/预留，
shared Bot 的后续 REPORT 也会含监控运行，因此可能重复上估。这些 allowance 不是
无条件的最大费用证明；只有完整 runtime 仪表/频率/通知重试限制接线后才能上线验证。

## 原子暂停与通知恢复

每次可选模型预留先强读当前月 AWS 行：必须有相同 inventory hash/价格版本、
ESTIMATE_VERIFIED、完整覆盖时间、新鲜观测（3 小时以内）及低于 90% 的金额。
随后同一 DynamoDB 事务检查 AWS revision/有效期/状态、原模型全局 CONTROL，并创建
一次模型 attempt 与原有 USD 7 账本扣款。监控并发修改导致事务冲突时不调用模型，
5 分钟后可再尝试；数据库故障也不能给 permit。

`check_aws_available()` 供可选确定性趋势刷新/样本处理的 AWS preflight，独立于模型额度；
它是一次强读，不是长期授权。`check_available()`/`reserve()` 是可选模型路径的组合门槛。
确定性 about/profile/forget 不应因为模型额度耗尽而关闭。监控/日志读取/通知恢复本身
必须绕过这两个 admission guard，否则会因自身暂停无法恢复观测。

缺/旧观测 5 分钟后可重测；AWS 90% 当月 sticky，到 UTC 新月也要先有新月观测。
模型 accounting anomaly 的全局 sticky CONTROL 不会被新月/新 AWS 观测解除。
监控故障持久化 UNVERIFIED 后显式抛错，由现有 Errors 告警处理。

AWS 行与最高阈值通知同一事务提交；MODEL 通知强读原账本并在事务里检查 charged 和
月/global paused，没有第二个 MODEL 写入者。通知 outbox 有独立全局索引，不依赖
事实 GSI 或 TTL。pending 无 TTL；SNS 确认 MessageId 后才 CAS ack。发送结果不明保留
相同事件与 observed_at，可能重复发送，由 Z17 去重；不宣称 exactly-once。
迟到低阈值不会覆盖更高状态。同一 scope/月只保存当下最高变化，超过 7 天的 pending
标为 EXPIRED，不刷新时间冒充新消息；每次处理最多 20 条。SENT/EXPIRED 元数据保留
400 天。只有既有 operations notifier 负责向正数 ADMIN_USER_ID 私聊。

## 公共接线接口与权限（本 slice 不执行）

所有相关 handler 获得同一个紧凑 `MEMORY_COST_INVENTORY` JSON；CloudFormation 部署后解析
account ID 等 token，统一 `parse_inventory` 在**运行时**展开闭合资源清单并计算完整 canonical hash。
env 只支持下述紧凑格式，避免完整清单约 2 KiB 导致 Bot 超过 Lambda 4 KiB 环境上限。
不能在 synth 时拿未解析
token 的字符串计算实际 hash，也不需要 CustomResource。Bot/worker 还必须配置
`MEMORY_COST_INSTRUMENTATION_SCHEMA=1`。collector 会读取每个实际函数环境中这两个
允许字段并检查相同 hash。以下为构造示例，未在 AWS 执行：

```python
inventory = parse_inventory(os.environ["MEMORY_COST_INVENTORY"])
budget = MemoryBudgetRepository(
    "zerde-serverless-memory-v2-prod", inventory_version=inventory.version
)
sdk_config = Config(connect_timeout=2, read_timeout=5,
                    retries={"total_max_attempts": 1})
# client(...) 是运行时 owner 按固定 region 和配置注入的 boto3 client factory。
telemetry = SDKCostTelemetry(
    inventory, cloudwatch=client("cloudwatch"), logs=client("logs"),
    dynamodb=client("dynamodb"), sqs=client("sqs"), lambda_client=client("lambda")
)
monitor = MemoryCostMonitor(
    budget, inventory, telemetry, sns=client("sns"),
    topic_arn=os.environ["OPERATIONS_TOPIC_ARN"]
)
monitor.run()  # 在现有 Bot 的 metered span 里；不得新增第二个通知 sender。
```

env JSON 的精确字段为 `schema=1, region="eu-central-1", account_id=<已解析12位账号>,
metering_started_at=<批准UTC秒>, alarm_count=10`，典型长度约 130 bytes。重复字段、未解析
token、额外字段或完整资源 JSON 不能作为第二种 env 格式。parser 展开上面的两环境闭合清单，
固定 `work-due`、dev PITR false / prod PITR true，再计算完整资源的 hash。直接
`CostInventory(full_document)` 仅用于显式程序构造/测试，不是第二个部署配置来源。
目录缺失/非法时 `MemoryBudgetRepository` 的默认构造也会保持无 permit。

所需权限由 infra owner 精确接入：CloudWatch GetMetricData；指定组的 Logs
DescribeLogGroups/StartQuery/GetQueryResults/StopQuery；指定表 DescribeTable/
DescribeContinuousBackups；指定队列 GetQueueAttributes；指定函数 GetFunctionConfiguration/
ListProvisionedConcurrencyConfigs；prod 费用前缀的 GetItem/Query/PutItem/UpdateItem/DeleteItem
和事务；向唯一 prod operations topic 的 Publish。Query/Delete 用于费用通知 outbox，
不能扩展为 dev 读取 prod 个人事实。某些监控 API 仅支持 `Resource:*`，仍由代码固定
names/region/查询，IAM 能细分的资源须细分。

保持每小时一个生产 owner、短 SDK 超时和有限平台重试。AWS Budgets 激活、cost allocation
tag 激活、部署、启用学习和实际通知另按 [operations runbook](OPERATIONS.md) 的授权步骤。
不要手改 AWS 行为 VERIFIED 绕过仪表。无法恢复过期历史时保持停止，等待下一 UTC 月的
完整计量，或先有独立审阅的历史重建方案。

## 本地证据与上线门槛

`tests/test_memory_cost_monitor.py` 使用真实 boto3 Resource + Moto 事务，CloudWatch、Logs、
SNS 全为 fake；同跑 `tests/test_memory_budget.py` 和 extraction budget 回归。
覆盖竞争、跨月、过期观测、数值损坏、缺 idle 资源、历史补齐、REPORT 缺项、查询超时、
扫描超额、SNS unknown 和通知账本 fence。本地不运行真实 Logs Insights 解析器。

上线前仍须公共仪表/全部入口接线、实际配置读回、真实无正文查询结果、零/非零样本、
暂停后无可选 provider attempt、恢复/私聊和账单差异核对证据。测试数不能替代这些验收。

### 暂停范围

模型门槛暂停个人事实抽取和记忆增强问答；AWS 估算门槛还暂停可选话题维护。为履行短期留存、故障恢复及未处理覆盖率契约，来源观察、30 天消息保存、待处理任务、安全审核恢复与更正/删除控制继续运行并可能产生 AWS 费用；暂停期间不会生成新的模型事实。恢复后只能处理仍有效且未逻辑到期的来源，过期必须计入覆盖率。此策略不声称停掉全部 memory AWS 消耗，也不提供 AWS 账单硬上限。若未来要停止新原文摄取，应作为单独数据覆盖率/恢复契约变更评审。
