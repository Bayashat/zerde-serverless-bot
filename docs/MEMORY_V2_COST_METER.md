# Memory V2 共享 AWS 用量计量（Z08 runtime 组件）

这是共享资源新增用量的保守归因器，不是账户账单硬上限。模型调用由 `memory_budget.py` 的独立账本负责；独立 V2 表、专用 queue/DLQ 由 CloudWatch/成本采集器负责，本组件不会重复计入。具体美元价格、月度预算暂停、告警和供应商结算仍由对应 owner 负责。

本 slice 只新增 `services.memory_v2.cost_meter`、直接测试和文档。Bot/worker 的 main/finally、V2 span、共享 SDK factory 及部署 inventory 的接线由集成 PR 完成。没有调用真实 AWS/模型/Telegram，没有部署，也没有得到真实账单验收。

## 精确接线契约

创建一次 `InvocationCostMeter(context, inventory, emit=..., clock=...)`；`request_id` 只能来自 `context.aws_request_id`。每个 V2 操作以 `with meter.span():` 包裹，可嵌套、可多段；首次进入才发 Start。Lambda 最外层 `finally` 调用一次 `meter.finish()`，必须先等待所有线程/异步任务完成，不能把后台任务留到 Final 之后。未触及 V2 的 Bot invocation 不输出这些 marker。

`register_client(client)` 在 `_common` / SQS 等可信共享 factory 中，对每个真实 SDK client 安装 hook；只安装，不调用 AWS。必须传 `resource.meta.client`，不是 DynamoDB Table/Resource 外壳。安装幂等、注册失败返回 False，并令本进程后续计量不可确认。DynamoDB 与 SQS 两类 hook 都必须已成功安装。

`CostInventory` 必须注入精确共享 stats 表名、主 queue URL、明确排除的其他表/专用 queue URL 集合和 `version`。名称/URL 完全匹配，不通过 `memory` 前缀猜资源归属。`version` 由集成层对已解析的 `MEMORY_COST_INVENTORY` 计算，不能添加另一个配置真源；该组件不要求新的 VERSION 环境变量。

`factory_coverage_verified` 默认 False。共享 stats 的 index/replica 数默认未知，必须根据已审计的部署清单明确传入 `shared_stats_index_count=0`（GSI+LSI）和 `shared_stats_replica_count=0`。当前仓库定义和只读审计均为零；配置未知或以后新增索引/副本时不能继续使用这些单位上界。主队列重投条件须与已批准 `maxReceiveCount=3`、消息上限 1 MiB 一致，否则 `complete=0`。

客户端完全绕过已接线 factory 时，该 client 没有 observer，自然无法在运行时从“未观察到调用”推断它不存在。部署 inventory、所有相关 factory 的代码审阅、注册成功及 collector 的 instrumentation schema 校验共同组成完整性证据；未完成这些接线时必须保留 `factory_coverage_verified=False`。不能仅安装某一个 client 就宣称所有 SDK 路径已覆盖。

日志使用共享 JSONFormatter 的 `_extra`，字段出现在外层 JSON：

```json
{"cost_event":"MemoryV2CostStart","cost_schema":1,"request_id":"Lambda request ID","memory_request":1}
{"cost_event":"MemoryV2Cost","cost_schema":1,"request_id":"Lambda request ID","complete":1,"elapsed_ms":12,"shared_stats_rru":100,"shared_stats_wru":0,"shared_sqs_units":115}
```

Start 每 invocation 最多一次，Final 最多一次；缺 id、未结束 span/SDK call、负/非法时长、未知资源/API/请求形状、注册失败或清单不完整均令 Final `complete=0`。日志 emit 失败不会覆盖业务异常：缺 Start/Final 由 collector 的逐 request 对账识别。collector 必须将每个 request 的 1 Start / 1 Final / 1 REPORT 独立对齐，不能只比全局总数以免遗漏和重复互相抵消。最终采集输出不包含 request ID/正文。

组件自身只发两个固定形状、无正文 marker，并核对加上格式化余量后不超过 64 KiB；超过则不完整。collector 另外为每个 Bot V2 invocation 预留 64 KiB 增量日志费用，并按完整 REPORT 计入保守 Lambda 时长，而不是把 `elapsed_ms` 当精确新增计费时间。

## SDK 尝试、单位与结算

固定依赖中的 botocore 在每次 endpoint 重试时重新触发 `before-send`。`before-call` 创建仅含计数/归属的调用状态，保存在 SDK context 及 ContextVar 栈；`before-send` 读取实际 prepared request 的 JSON 进行精确资源识别，立即预记单位；正文、key、chat/user ID、URL、header 和异常文本均不持久化或写入 marker。重复 JSON 属性和无法识别的 wire shape 不能绕过归因。

监控器对精确 `excluded_tables` 名单执行的 `DescribeTable` / `DescribeContinuousBackups` 由 monitor 的 API 预留负责，本 meter 记零共享单位。相同 API 指向共享 STATS 或未知表仍为 `complete=0`；这不是所有 control-plane API 的通用豁免。

| 共享资源动作 | 每次 wire attempt 预留 |
| --- | --- |
| DynamoDB GetItem | 100 RRU，按单项最大 400 KiB、强一致读取 |
| PutItem/UpdateItem/DeleteItem | 400 WRU + 100 RRU，额外读覆盖失败旧值/条件检查的保守余量 |
| Query/Scan | 256 RRU，按每页 1 MiB 强读 |
| BatchGetItem | 每 shared key 200 RRU，最多 100 keys；额外乘二为保守余量 |
| BatchWriteItem | 每 shared write 800 WRU + 200 RRU，最多 25 项；额外乘二为保守余量 |
| TransactGet/ConditionCheck | 每 shared action 200 RRU |
| TransactWrite 的 Put/Update/Delete | 每 shared action 800 WRU + 200 RRU |
| SQS SendMessage | 115 request units |
| SQS SendMessageBatch | 每消息 115 units，上限 10 消息，保守重复计算 batch 发送本身 |
| SQS ReceiveMessage | 每请求最多消息数 × 16 units，上限 10 × 16 |
| SQS Delete/Visibility/GetAttributes | 每次 1 unit；batch 按每 entry 1 unit，上限 10 |

DynamoDB batch/transaction 逐项按最大项目计入，不利用整体 16/4 MiB 限额进一步缩小，是有意上估。事务失败仍保留预记量，不把条件失败当零成本。[AWS 读写计费规则](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html)、[事务限额与双倍底层操作](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html)、[BatchWrite 限额](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html) 是这些单位的基础。

SQS 每消息上界为 `16 send + 3 × (16 receive + 1 delete + 16 DLQ) = 115`。64 KiB 是一个计费 payload 单位，1 MiB 对应 16 个；DLQ 并不一定另收费、更不会每次都发生，因此这里是故意上估的未来处理预留。若未来实际共享 consumer SDK 调用也被捕获，允许保守重复计入，不引入容易漏账的跨 invocation 抵扣。该估算依赖批准的队列重投/消息大小边界，不覆盖无限人工 redrive；不满足边界时必须标不完整。[SQS 计费](https://aws.amazon.com/sqs/pricing/)、[SendMessageBatch 上限](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_SendMessageBatch.html)。

对已知支持的 DynamoDB 操作，V2 span 内自动请求 `ReturnConsumedCapacity=TOTAL`，保留显式 `INDEXES`。仅当 HTTP 成功且返回所有 shared table 的完整、合法 `ReadCapacityUnits` 和 `WriteCapacityUnits`，才用实际数值调整 **最后一次 attempt** 的预留；之前未知重试、失败/异常响应完全不退。只返回合计 CapacityUnits、缺字段或无 CC 时保留上界，不冒险拆分读写方向。SQS 不根据成功响应退款，因为发送未知和后续 consumer 成本仍需要覆盖。

## 验证边界

测试使用真实 botocore 的 before-send/retry/after-call 路径及 fake HTTP session，另有 Moto Resource 原生序列化/事务验证；不使用 Stubber 返回值冒充真实 wire attempt。涵盖 500 后重试、连接失败、条件失败、最后一次 CC 结算、mixed-table transaction、批量和 consumer 上界、scope 外排除、warm invocation、嵌套 SDK、`asyncio.to_thread` ContextVar、实际 prepared body 变化、缺 hook/inventory、JSON 外层字段及无正文日志。

这些是本地工程证据，不是实际 AWS 费用。只有公共接线、部署清单读回、逐 request collector 对账和计费窗口数据齐全后，才能把估算标为有完整输入；不能据此承诺 AWS 账户硬封顶。
