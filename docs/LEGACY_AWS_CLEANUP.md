# 旧 AWS 资源清理手册（Z18）

状态：**清理候选已审阅；未执行删除。** 关联 [Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)、[Z18 #175](https://github.com/Bayashat/zerde-serverless-bot/issues/175)。基线为 `2f3abe7`，审计日期为 2026-09-10。此文档不是 Memory V2 清零工具；当前 memory 表和向量索引的内容清理由 Z10 单独管理。

## 固定范围

全部候选均在 `eu-central-1`。2026-09-10 只读审计覆盖了 17 个已启用区域的 CloudFormation 及项目名称匹配的 Lambda、DynamoDB、SQS、Logs、HTTP API、EventBridge、S3 Vectors。名称完全不包含项目标识的孤儿资源不能因此排除。

| 服务 | 精确资源标识 | 审计证据 | 后续动作 |
| --- | --- | --- | --- |
| DynamoDB | `zerde-prod-bot-stats` | 12 行，2272 B；90 天读写为零；不属于当前 stack，当前 Lambda 无引用；PITR 和删除保护仍开 | 重新核验消费者、备份及恢复后，单独申请删除该表 |
| SQS | `zerde-prod-updates-queue` | 空；90 天无流量；没有 Lambda event source mapping 或 queue policy | 复查生产者、目标、重驱引用及全部三类在途计数后清理 |
| SQS | `zerde-prod-updates-dlq` | 同上 | 先处理源队列，再处理 DLQ |
| Logs | 两个旧 `TelegramBotStack-dev-LogRetention…` 日志组，完整名称见下方清单 | 对应 Lambda 已不存在，存储为零 | 以完整名称逐个清理 |
| Logs | `/aws/lambda/tg-dev-receiver`、`/aws/lambda/tg-dev-worker` | 对应 Lambda 已不存在，存储为零 | 以完整名称逐个清理 |

完整日志组清单（2026-09-10 再次只读列举，四组 storedBytes 均为 0）：

```text
/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-VOs3WfeNiAH7
/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-Vz797oVzECIN
/aws/lambda/tg-dev-receiver
/aws/lambda/tg-dev-worker
```

**不在删除范围：** 当前 dev/prod stack、当前业务/Memory V2 表与队列、共享 CDK assets bucket、其他项目资源、用户电脑上的 Telegram 导出文件。旧 SSM 参数 `/zerde/bot/token`、`/zerde/bot/webhook_secret` 的外部脚本消费者尚未查清，只可继续调查，不能随本批删除。不要读取或输出参数值。

候选主要改善资源卫生，节省很小。dev 空轮询与告警费用归 Z17 管理，不能据此删除整个 dev stack。账单没有项目成本分配标签时，不把账号总额归因给本清单。

## 执行前证据包

实际删除需要后续明确授权，授权必须包含本次精确资源清单。执行者将以下结果保存至受限目录（`umask 077`），记录账号、region、UTC 时间、CLI 版本和 source commit。审计旧快照不能代替删除前读回。

1. 用 `aws sts get-caller-identity` 核对账号，并固定所有命令的 `--region eu-central-1`；账号不符即停止。
2. 导出当前 stack 的资源清单；排除当前 stack 所有 physical resource ID。查 Lambda 配置时在内存中比较资源标识，只输出引用函数名/环境变量键，不输出整份环境变量或任何密钥。
3. 列出 Lambda event source mappings、相关 EventBridge target、CloudFormation 资源、当前代码和部署 workflow 中的引用。检查运行者维护的外部脚本；无法确认时记录为 unresolved，不把“代码里没找到”当成无人使用。
4. 对旧表，保存 describe-table/TTL/PITR 元数据、过去 90 天读写统计和扫描行数。CloudWatch 没有 datapoint 是 **UNKNOWN**，不是零。重新枚举表项时只在加密备份中保存内容，日志只保留计数和摘要。检查是否存在全局表副本、stream 消费者、备份和 PITR 保留成本。
5. 对每条队列分别读取 `ApproximateNumberOfMessages`、`ApproximateNumberOfMessagesNotVisible`、`ApproximateNumberOfMessagesDelayed`、`RedrivePolicy`、`RedriveAllowPolicy`、`Policy` 和队列 ARN；三个计数都必须为零。枚举其他队列的重驱关联，以及 Lambda/事件目标和外部生产者。停止/移除生产者后重新观察一段覆盖最长生产周期的窗口；“此刻为空”不等于废弃。
6. 对每个日志组确认 Lambda 不存在、storedBytes 为零、最近没有事件、没有 subscription filter；重新检查 retention 和对应资源归属。列表分页必须耗尽。
7. 任一读取失败、权限不足、依赖未确认、近期出现流量、资源身份变化时停止该资源的删除。仍可继续其他已独立验证的资源。

可用的只读命令模板：

```bash
aws dynamodb describe-table --region eu-central-1 --table-name zerde-prod-bot-stats
aws dynamodb describe-continuous-backups --region eu-central-1 --table-name zerde-prod-bot-stats
aws dynamodb describe-time-to-live --region eu-central-1 --table-name zerde-prod-bot-stats
aws sqs get-queue-url --region eu-central-1 --queue-name zerde-prod-updates-queue
aws sqs get-queue-url --region eu-central-1 --queue-name zerde-prod-updates-dlq
aws lambda list-event-source-mappings --region eu-central-1
aws logs describe-log-groups --region eu-central-1 --log-group-name-prefix /aws/lambda/TelegramBotStack-dev-LogRetention
```

`get-queue-attributes` 的 `--queue-url` 必须使用本次 get-queue-url 返回值，不能手写另一个账号的 URL。源队列和 DLQ 都要读取全部属性，但不要将包含其他项目策略的原始文件贴到公开工单中。审核分享文件只保留本项目依赖和必要计数。

## 后续获准后的操作顺序

本次没有执行下列写操作。执行时每一步记录结果，失败不跨过前置检查。

### 旧统计表

1. 为精确表建立一个按需备份，等状态 AVAILABLE；记录加密配置、备份 ARN、删除期限和负责人。PITR 不是永久保留备份。
2. 用此备份恢复到**新的临时表名**，比较 item 数量与规范化数据摘要；确认可读后删除临时恢复表。恢复验证失败不得删除原表。
3. 单独关闭原表 deletion protection，等 ACTIVE，再次比对 table ARN/创建时间，然后删除这一个表。不要让通用脚本按 `zerde*` 批量删除。
4. 读回 ResourceNotFound 才标记表删除完成。保留期到期后独立删除按需备份并验证；尚有备份/PITR 恢复副本时只能声明在线表不存在，不能声明物理副本全部清除。
5. 如需回退，恢复至新表并显式更新消费者引用；恢复不会自动找回原表的 stream ARN、TTL、PITR、告警或 IAM 绑定，需逐项恢复并读回。若原本无消费者，不为回退临时接入当前 bot。

### 旧队列

1. 保存队列配置及来源证据，不调用 `PurgeQueue`。混合业务队列不在范围内。
2. 先删除 `zerde-prod-updates-queue`，确认其不存在且其他源队列未依赖该 DLQ，再删除 `zerde-prod-updates-dlq`。
3. 队列删除不具备消息恢复能力；重新创建同名队列不等于恢复原来的队列、消息、映射或权限。若发现仍有生产者，应立即停止批次并处理生产者错误，不能声称删除可无损回滚。

### 空孤儿日志组

按完整名称逐个删除，读回不存在；不删除整个前缀。若出现新事件或非零存储，应回到范围审阅；有保留需求时先导出并验证备份。已删除的日志事件无法靠重新创建同名日志组恢复。

## 验收、退出与记录

- 每个对象记录：授权引用、before/after UTC、精确 ARN/创建时间、依赖证据、备份/恢复结果、删除 API 结果、读回结果、剩余副本和清理期限。
- 当前 stack 的资源集、业务表计数、队列 mapping、bot 健康和业务告警应与操作前相符；本手册不授权发送真实 Telegram 测试消息。实际业务 canary 在另行授权的验收阶段记录。
- 不用“Delete API 返回成功”代替资源不存在的读回，也不用“无读取指标”代替消费者核验。
- Z18 的本地交付是精确候选和手册；**实际云资源删除保持未执行**。不得关闭实际删除的执行记录或填入未经观察的节省金额。
