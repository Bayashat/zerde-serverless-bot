# 运维通知、dev 按需运行与恢复（Z17）

关联 [Z17 #174](https://github.com/Bayashat/zerde-serverless-bot/issues/174)、[Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)。打包基线依赖 [Z04 #183](https://github.com/Bayashat/zerde-serverless-bot/pull/183)。当前交付是本地代码、测试和操作手册；尚未部署、激活成本标签、创建 AWS Budget、发送 Telegram 或恢复真实表。状态为 **IMPLEMENTED_UNPROVEN**，生产验收不能由测试替代。

## 运行开关与计费归因

`DEV_RUNTIME_ENABLED=false` 是 dev 默认值。最终集成包含六个 Lambda：Bot、vector-indexer、News、Quiz、operations notifier 和 Memory V2 worker；dev 的 reserved concurrency 均为 0，主队列、向量队列和 Memory V2 队列共三条 SQS event source mapping 关闭，恢复调度停用，dev 不创建付费 CloudWatch alarms。明确设为 `true` 后恢复相应并发设置和告警；prod 始终启用。consumer 的 maximum concurrency 为 Bot 10、vector 3、Memory V2 worker 2；worker 的 reserved concurrency 为 2。业务 Lambda 在 prod 的 reserved concurrency 保持原状。所有入口和 worker 共用 stack 的 `runtime_active`，不存在单独默认常开的 dev Memory V2 消费路径。

关闭 dev 前先停止新任务来源，确认所有时间敏感业务任务完成或有明确恢复处置，并读取所有当前已部署 Lambda 的 timeout，按其中最大值等待并确认在途 invocation 排空；审计发现旧部署曾有 900 秒 worker，源码的 300 秒不能代替 live readback。然后部署相应开关。开关不会清空队列或重置数据库；暂停期间 Telegram webhook 可能因 Lambda 节流而不断重试并积压。重新启用前检查 Telegram pending update、SQS visible/inflight/delayed 三类计数和最旧任务年龄，审查过期的 join/captcha/vote/contest/AI 任务。不要无条件重放旧更新，也不要通过 PurgeQueue 隐藏积压。启用必须有当前测试身份、群映射和 token 的明确隔离；这一开关不能证明 dev 与 prod 的 Telegram 身份已分离。

所有支持标签的 stack 资源继承 `Project=ZerdeBot` 和 `Environment=dev|prod`，业务 construct 再标注 `Component=bot|vector-indexer|news|quiz|messaging|operations`；Memory V2 worker/queue construct 使用 `Component=memory-v2`。CDK layer、共享账户服务、未支持/未继承标签的计费项仍可能无法分摊，不把它们算作零。

标签存在与成本分配标签生效是两步。标签可能需最多 24 小时出现，再需最多 24 小时激活；激活影响同名键的所有值。新增标签不能凭空恢复过去缺失的项目归因。本轮不申请历史回填。[AWS 激活说明](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/activating-tags.html)

获准部署后，先核对账号、region 和实际资源标签，再在管理计费的账号执行以下单独获准的激活操作。`update` 是写操作，本轮未执行；逐项检查 `Errors`，不能只看 CLI 返回 0。

```bash
aws ce list-cost-allocation-tags --region us-east-1 --tag-keys Project Environment Component
aws ce update-cost-allocation-tags-status --region us-east-1 --cost-allocation-tags-status '[{"TagKey":"Project","Status":"Active"},{"TagKey":"Environment","Status":"Active"},{"TagKey":"Component","Status":"Active"}]'
aws ce list-cost-allocation-tags --region us-east-1 --tag-keys Project Environment Component
```

未来完整周期的只读归因示例，`START` 和 `END` 必须填写已发生的 UTC 日期，结束日期不包含在区间内：

```bash
aws ce get-cost-and-usage --region us-east-1 --time-period Start="$START",End="$END" --granularity MONTHLY --filter '{"Tags":{"Key":"Project","Values":["ZerdeBot"]}}' --metrics UnblendedCost --group-by Type=DIMENSION,Key=SERVICE Type=DIMENSION,Key=RECORD_TYPE
aws ce get-cost-and-usage --region us-east-1 --time-period Start="$START",End="$END" --granularity MONTHLY --filter '{"Tags":{"Key":"Project","Values":["ZerdeBot"]}}' --metrics UnblendedCost --group-by Type=TAG,Key=Environment Type=TAG,Key=Component
```

记录响应的 currency、estimated、usage、credit/refund、tax 和 net；另列无法标签分配的费用。账户总额、Zerde 可归属额、Memory V2 增量额是三种口径。USD 3 是 V2 新增 AWS 预算，不是整个旧 bot 的 AWS 月上限；operations 资源的归属/共用分摊也须进入增量估算，不能因标签为 operations 而漏掉。

最终每个活跃环境有 **22 个告警**：四个业务 Lambda 各三个，共 12 个；主/向量 DLQ 两个；operations 三个；Memory V2 worker/队列五个。dev 停用时为 0，因此 prod 活跃而 dev 停用共 22 个，两环境都活跃共 44 个，不是 27 个。成本 inventory 的 `alarm_count=10` 只表示两环境最多十个 **Memory V2 新增告警**的整月毛价预留；dev 停用也不退回这项预留，它不是 stack 告警总数。通知 Lambda/SNS/状态读写按事件使用，没有额外常开 SQS poller。真实节省和费用应以部署后同等观察窗口及 CE 为准。

与 Z13 同批集成时，`KICK_BAN_DURATION_SECONDS` 默认及有效下限统一为 60 秒，旧 31 秒配置规范化到 60；这是为 Telegram 临时封禁运输窗口作出的必要安全修正，不改变临时封禁性质或其他审批阈值。

## 通知所有权与失败恢复

`OperationsConstruct` 提供独立 SNS topic、notifier Lambda、SNS subscription delivery DLQ 和 Lambda execution DLQ。前者处理 SNS 未能交给 Lambda 的情况，后者保留 Lambda 已接受但执行失败/重试耗尽的事件；这两个失败阶段不可混为一谈。AWS SNS 与 Lambda 都可能重复投递。[SNS 重试](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html)、[Lambda 异步错误处理](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)

notifier 只接收已配置 topic，核对注册的 alarm 名称、账号、region/ARN、事件时间；只发送 ALARM、从 ALARM 恢复的 OK 和受限预算事件。它不转发原始 reason/body 或用户自带 text/destination。目的地只能是已配置的正整数 `ADMIN_USER_ID`，Telegram 回执也必须确认相同 private chat。管理员需先与 bot 建立私聊；未配置、403、429、超时、无法确定发送结果或 DynamoDB 故障都会失败并进入重试，不伪装成功。

通知状态仅使用现有 stats 表的 `operations#<stream hash>`，IAM 限定此 key 前缀的 GetItem/UpdateItem；不读写其他业务记录。90 秒 lease 大于 notifier 的 60 秒 timeout；旧 lease 不能确认新 owner 的发送。已确认事件的相同/更旧时间不重复发送。发送成功但确认写入失败时仍可能重发，这是显式的 Telegram/DynamoDB 跨系统窗口，不声称 exactly-once。状态 TTL 30 天；超过 7 天的通知拒绝自动重放并保留为失败，避免把旧恢复/旧预算作为当前状态发出。

注册业务告警时调用 `operations.register(alarm)`，alarm 必须有明确稳定名称；统一添加 ALARM 与 OK SNS action。不要另写第二个 Telegram 通知出口。Memory V2 worker 已注册 Errors、Throttles、Duration p95、DLQ visible 和 queue age 五个告警；实际部署后的阈值、action 和通知送达仍须读回验收。`verify_lambda_bundles.py` 已明确注册上述六个包及 handler，未知或缺失包均失败；prod 小时成本监控复用 Bot，不新增第七个 Lambda。

故障恢复步骤（后续获准操作）：

1. 只读查看 alarm 状态、SNS delivery failure 指标、notifier Errors/Throttles/AsyncEventsDropped、两个 DLQ 的 visible/inflight/delayed 计数。notifier 自身损坏时同一 Telegram 通道也可能失效，AWS 控制台/DLQ 是独立的人工检查入口；不把“已有 SNS action”当作管理员已收到。
2. 检查正数管理员 ID、bot 私聊权限、notifier SSM 仅 bot-token 权限、stats 的 operations 前缀权限和 KMS 条件。不要输出 token、SSM 值、HTTP URL 或原始事件正文。
3. 修复原因后，在受限位置检查 DLQ 的 SNS envelope 元数据。原始 SNS delivery DLQ 与 Lambda execution DLQ 的封装不同，先提取并校验 TopicArn/MessageId/Timestamp/业务 observation，再按原 envelope 重放到 notifier。不要把整个 DLQ 内容直接 publish 回 SNS，当成新事件刷新时间。
4. 恢复只重放经核验的近期事件，保留原 observation 和身份。已确认更晚的事件会忽略旧事件；过期事件先人工核实当前 alarm/预算状态，记录处置，必要时由原 owner 发布当前新事件。成功确认后才从 DLQ 删除对应消息。两个 DLQ 保留 14 天，不能无限等待人工处理。
5. 实测一条受控故障及其恢复通知确实只到管理员私聊，并记录 Telegram 回执 ID、时间、目标核验及 DLQ=0。此 canary 需要真实发送授权，本轮尚未执行。无此证据仍是 IMPLEMENTED_UNPROVEN。

## Z08 预算事件与可选 AWS Budget

Z08 是预算的唯一 owner，决定 USD 7 全项目模型硬预留、USD 3 增量 AWS 估算及暂停策略。USD 7 是项目总额，dev/prod 共享费用账本，不能各获一份；通知的 environment 仅表示发起运行环境，跨环境阈值去重由 Z08 的共享账本负责。它通过 `operations.grant_budget_publish(worker)` 获得 topic 的 Publish 权限，注入 topic ARN，持久化阈值事件并在重试时保留同一 `observed_at`。同一 environment/scope/period 共享通知 stream，按 observation 排序；同批跨过多个阈值时只发布最高有效状态，不在更晚时间发布过时的较低阈值。本组件不重新计算预算或暂停业务。以下为唯一可接受的预算消息格式示例（使用当前真实观察时间，不能复制旧日期上线）：

```json
{"schema":"zerde.operations.v1","kind":"budget","project":"ZerdeBot","environment":"prod","component":"memory-v2","budget_scope":"incremental_aws","threshold_percent":80,"status":"warning","period":"2026-09","observed_at":"2026-09-10T12:00:00Z"}
```

`budget_scope` 可为 `model` 或 `incremental_aws`，threshold 只允许 80/90/100，status 为 warning/paused；period 必须与 observation 的 UTC 月份一致。模型和 AWS 通知必须准确标注各自账本/估算来源。Z08 的持久化通知 outbox 和小时监控已在源码中接线，仍未经过生产送达与真实账单验收；不能称预算通知已全面工作。首次部署计费起点、完整计量和暂停范围见 [运行时契约](MEMORY_V2_RUNTIME.md) 与 [成本监控契约](MEMORY_V2_COST_MONITOR.md)。

AWS Budgets 是按账单刷新运行的辅助工具，不能提供模型级硬停止，也不能直接替代 V2 的增量估算。AWS 原生 Budget SNS 通知不是上面的 JSON 契约，**不要把它直接订阅到当前 notifier topic**。本阶段不启用 Budget SNS publisher，也不增设第二套解析逻辑。若需要单独的控制台费用 backstop，在成本标签有效后由账号 owner 确定整个项目的月金额，创建一个无订阅的 COST budget；其上限不能写成 V2 的 USD 3。金额和通知连接是后续明确配置与验收项。[AWS Budget 更新频率与边界](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-best-practices.html)

AWS Budgets 的 TagKeyValue 需要 `user:` 前缀（与 CE 的 Tags filter 形式不同），见 [AWS CLI 官方示例](https://docs.aws.amazon.com/cli/latest/userguide/cli_budgets_code_examples.html)。

精确 CLI 模板：保存经审核的 `budget.json`（将 `MONTHLY_PROJECT_AMOUNT` 替换为 owner 确认的十进制金额），先检查同名 budget，避免重复；创建是后续获准写操作，本轮未执行。

```json
{"BudgetName":"zerdebot-project-monthly","BudgetType":"COST","TimeUnit":"MONTHLY","BudgetLimit":{"Amount":"MONTHLY_PROJECT_AMOUNT","Unit":"USD"},"CostFilters":{"TagKeyValue":["user:Project$ZerdeBot"]},"CostTypes":{"IncludeCredit":false,"IncludeRefund":false,"IncludeTax":false,"UseBlended":false,"UseAmortized":false}}
```

```bash
aws budgets describe-budget --region us-east-1 --account-id "$ZERDE_ACCOUNT_ID" --budget-name zerdebot-project-monthly
aws budgets create-budget --region us-east-1 --account-id "$ZERDE_ACCOUNT_ID" --budget file://budget.json
aws budgets describe-budget --region us-east-1 --account-id "$ZERDE_ACCOUNT_ID" --budget-name zerdebot-project-monthly
```

`ZERDE_ACCOUNT_ID` 从本次 STS 身份核对后设置；不能用未审查的默认账号。readback 核对过滤器、gross 口径、currency 与金额；无历史预测数据不代表预测费用为零。不要声称创建 Budget 等于已限制 AWS 消费。

## Quiz PITR 与恢复

prod Quiz 表启用 7 天 PITR，保留原 Retain 与 deletion protection；dev 不启用。7 天是恢复副本的保留窗口，**缩短到 7 天不会降低 PITR 的按表大小收费**。[AWS PITR 说明](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html)

部署后读取：

```bash
aws dynamodb describe-continuous-backups --region eu-central-1 --table-name zerde-serverless-quiz-prod
```

必须看到 ENABLED、RecoveryPeriodInDays=7 和真实 Earliest/LatestRestorableDateTime。历史未启用的时间不能恢复。恢复练习需另获云写授权：选择窗口内 UTC 时间，`restore-table-to-point-in-time` 恢复到新的临时表名，等 ACTIVE；核对 schema、PollIdIndex、记录数量及规范化摘要，保护真实用户内容。新表需要独立检查 IAM、TTL、PITR、tag、stream/告警设置；恢复成功不会自动把当前 Bot/Quiz 指向新表。

```bash
aws dynamodb restore-table-to-point-in-time --region eu-central-1 --source-table-name zerde-serverless-quiz-prod --target-table-name "$ZERDE_RESTORE_TABLE" --restore-date-time "$ZERDE_RESTORE_AT"
aws dynamodb wait table-exists --region eu-central-1 --table-name "$ZERDE_RESTORE_TABLE"
aws dynamodb describe-table --region eu-central-1 --table-name "$ZERDE_RESTORE_TABLE"
```

业务切换前暂停 Quiz 写入、记录截止时间和恢复点后可能丢失的数据，评估是否需补录，再显式变更两条消费者引用并做 canary。保留原表以便回退；不要用恢复工具覆盖或删除现表。练习结束按保留期限清理临时表及副本，并分别记录读回。没有恢复演练和真实 readback 不能把 Quiz 灾难恢复标记为已验收。

## 本地验证证据（历史 Z17 slice）

下段保留 2026-09-10 Z17 初次交付时的结果：五个 Lambda、两条 mapping 和 17 个告警属于该提交时点，不代表当前最终集成，也不是 live 配置读回。当前源码的六个 Lambda、三条 mapping、每个活跃环境 22 个告警以上文为准；最终集成测试和打包证据单独记录在执行 EVIDENCE 中。

2026-09-10：624 项完整测试通过（1 个既有 google/genai DeprecationWarning），含 22 项通知/真实 SDK + Moto 故障恢复测试及 dev idle/active、prod、权限、17 告警 action、PITR 模板断言。tracked 与新增文件 pre-commit 通过；根锁导出 --check 通过。真实 CDK Docker 打包成功，5 个严格注册 handler 在固定 AWS ARM64 Python 3.13.15 runtime 镜像中、network=none 下全部导入通过，SDK 来自资产目录。只读 dev `cdk diff --no-change-set` 成功，显示 14 个旧 dev alarms 删除、4 个业务 Lambda reserved concurrency 归零、两个 mapping 停用及独立 notifier/SNS/双 DLQ/标签变化；其中还包含 Z04 依赖和未设置本地生产变量引起的配置差异，因此不是获准部署清单。以上均不代表真实通知送达、AWS 标签生效、dev 用量减少或 PITR 已开启。
