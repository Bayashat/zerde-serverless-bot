> 历史阶段契约；当前执行入口为[HANDOFF](HANDOFF.md)。本文件已有清理/发布均不得因旧措辞重跑；最新结果见[最终在线退役](evidence/2026-09-28-legacy-stats-final/final.safe.json)。

> 2026-09-28 R3入口复核更正：下文历史Quiz示例中的逗号会被现有parser并入topic，令difficulty回落medium。实际验收使用 `/genquiz@zerde_dev_bot Python easy ru`（空格分隔）；旧示例不再作为执行指令。

# 更早空资源退役契约（2026-09-28）

本批接续 [FINISH_EXECUTION](FINISH_EXECUTION.md) 的 R2/Z20，执行结果以 [task_manifest](task_manifest.json) 和独立 AWS 读回为准。S4 已完成的 28 对象不重复处理。主代理已在本对话告知下列准备删除、保留与待核实项；不要求重复授权。

## 精确范围

区域固定 `eu-central-1`，不按通配符删除。

| 准备退役的对象 | 精确名称 |
|---|---|
| 旧主队列 | `zerde-prod-updates-queue` |
| 旧死信队列 | `zerde-prod-updates-dlq` |
| 旧日志组 | `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-VOs3WfeNiAH7` |
| 旧日志组 | `/aws/lambda/TelegramBotStack-dev-LogRetentionaae0aa3c5b4d4f87b-Vz797oVzECIN` |
| 旧日志组 | `/aws/lambda/tg-dev-receiver` |
| 旧日志组 | `/aws/lambda/tg-dev-worker` |

保留六张现役 stats/Quiz/V2 表、当前函数/层/队列/日志、控制和预算。`zerde-prod-bot-stats` 及两个旧 SSM 参数不在本批删除范围，不读取或打印参数值。

## 执行与验收

1. 固定账号、ARN/URL、创建时间和原配置，核验当前栈、Lambda 版本/事件映射、EventBridge、Scheduler/Pipes、SNS 和 API 接线无引用。未知或进行中的依赖使本批停止。旧 90 天指标缺口保留 UNKNOWN，不拿没有数据点证明零使用。
2. 两队列必须三类深度为零，只有固定主队列指向本 DLQ，无进行中的消息移动任务。只给这两条旧队列添加精确流量 Deny，原配置留在私有记录，不修改当前混合队列。等待至少 65 秒后，读回完整 Deny 和三类零深度；从这次读回结束再等待至少 90 秒，然后重新查依赖、身份和空状态。此证据不是 AWS 原子空快照或未来流量承诺。
3. 四个日志组要求身份/保留期不变、源函数不存在、组 storedBytes 为零、完整日志流集合和活动字段匹配、过滤事件结果为空、没有订阅/指标过滤器或进行中/未知状态导出。只排除已弃用的 `uploadSequenceToken` 并规范顺序，不放宽新增流或内容变化。[AWS 字段契约](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_LogStream.html)。
4. 每次云写先保存不可覆盖的 intent，SDK 不自动重试。先删主队列，明确 NotFound 且 DLQ 来源引用消失后才删 DLQ，再逐个日志组删除。任何不明响应先只读对账，不重发 intent，不运行已完成的旧脚本。
5. 独立核验六对象不存在。删除前后比较六现役表及保留旧 stats 表的身份/保护字段、十个现役 Lambda 的包/层/环境/角色/handler/runtime/容量摘要；这只是本次保护投影，不冒充重新完成全部发布验收。没有写表、CONTROL、预算或模型调用。

恢复只保留空资源定义；重建同名队列或日志不能恢复其内容。历史导出和外部副本未穷尽，不宣称全副本抹除。原 10 月 4 日临时 AV、10 月 17 日 PITR、11 月 1 日 SYSTEM 副本义务分别保留。

## 剩余旧表的实际判断

以此前冻结的旧表 12 行快照为源，对现役 prod stats 表的对应精确键进行了强读对照：4 条历史累计统计中，3 条在现役同键的 started_at 相同，相关计数均不低于旧值；第 4 条没有现役对应行。8 个旧投票在现役同键都不存在，不能据此宣称过期或已迁入。当前代码无旧表 fallback，不迁入这 8 条旧会话使其复活。

旧表后续要明确保全剩余有效统计、退役旧投票运行状态、验证备份与恢复，然后另列删除清单。现有临时 AV 文件不代替按需备份及恢复验证。两旧 SSM 参数继续按已知代码/配置/访问证据核实消费者；不要求证明所有未知客户端从不存在，也不在未闭合边界时删除。

本批不启用新功能、新群或 prod 记忆；R2 整体、业务恢复验收和自然使用门槛仍分别开放。真实 Quiz 补测需使用现有支持语言 kk/zh/ru，例如 `/genquiz@zerde_dev_bot Python, easy, ru`；此前研究中的 en 示例无效，尚未据此执行或宣称验收。
