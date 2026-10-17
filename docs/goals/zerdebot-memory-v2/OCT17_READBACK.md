# Oct17 PITR 到期复核与首发第三天观察

这是已完成的有限只读结果；文档发布不是运行部署。主代理串行执行，主/独操作不并行；顺序读取不是全局事务。当前功能保持 **RELEASED_OBSERVING**。

## 旧 memory PITR

原35日职责期限2026-10-17 16:20:38UTC不改。主5读首意图16:20:38.287728UTC，独立5读首意图16:21:03.758355UTC；主实际晚0.28772807121276855秒，原因UNKNOWN。按原ARN/TableId与区域/账号核验：DescribeTable为ResourceNotFoundException，DescribeContinuousBackups为TableNotFoundException，HTTP400、RetryAttempts真正整数0；旧表和PITR入口不存在，窗口字段不可读。精确table-bound ALL备份页完整，仅1个原SYSTEM备份AVAILABLE，原2026-11-01 11:46:02.425UTC期限保持。

原PITR到期复核职责完成；不声称全部云副本消失、AWS Backup vault全量盘点、恢复测试或物理擦除。37在线退役数不增。[主聚合](evidence/2026-10-17-readback/pitr.safe.json)及[实际独审](evidence/2026-10-17-readback/pitr-independent.safe.json)。

## 首发第三天

四群中文-1002211083217、哈萨克语-1001244628965/-1001450935528/-1004490324695，独立fresh CONTROL均ACTIVE/learning=true/首发epoch一致，时点revision1；未来合法业务可推进revision，不强写回历史值。

原Observe20261017A在第26读遇到空epoch门禁后真实PARTIAL_UNKNOWN/row_epoch停止。原源码、报告和26响应不改；新窄合同只续接未读范围，另4身份读合计15，再独立10读。共51 API，原26不重跑。返回ANSWER页共25条空epoch旧SENT，全部首发前、原因UNKNOWN；当前首发epoch SENT共4（中文0、三哈群2/1/1），不等于完整答案质量或自然样本。

8个WORK/ANSWER返回页中，后三群WORK各第一字典序25条且有续页，不跟页、不称最新排序或完整积压。四群WORK返回页81条业务状态为79 DONE/2 EXPIRED；这里没有把状态EXPIRED当正常完成。覆盖计数按UTC日，缺行ABSENT；不相减推积压，不汇总成精确启用后用户数/调用数。主采集截止基准1792254588.2749171；不是跨行一致快照。

第四群News Oct15/16/17的保存步骤各4条SENT并有发送回执；Quiz Oct15/16 owner DONE并有poll/message回执。四CONTROL与Oct15News/Quiz共6投影经独立fresh逐项相同；其他日期/计数/页是主读取后独立直接原响应核验。没有完整News manifest、Quiz三行一致性或原生Telegram现场，周榜未覆盖。首发配置中中文News为DISABLED；本轮未重新读取该配置，没有手动补发/Invoke/模型/数据写。不能据此关闭原News恢复或Quiz重送缺口。

自然仍0/50有据、0/20未知、起点null，production_ready=false表示完整自然质量未验收；当前公开功能已启用。没有读取完整答案/来源语义，没有新增自然样本；下一Oct21首周、后续每周有限观察。[安全聚合](evidence/2026-10-17-readback/observation.safe.json)、[独立POST](evidence/2026-10-17-readback/observation-independent.safe.json)、[总回执](evidence/2026-10-17-readback/completion.safe.json)。

## 副本期限（UTC）

|序号|职责|原精确期限|实际文件数/动作|
|---|---|---|---|
|1|prod-errors-raw|2026-10-20T14:32:29.705948+00:00|341|
|2|launch-raw|2026-10-21T13:10:50.198516+00:00|527|
|3|pitr-readback-raw|2026-10-24T16:20:38.287378+00:00|10|
|4|day3-observation-raw|2026-10-24T16:29:48.470834+00:00|51|
|5|old-memory-SYSTEM|2026-11-01T11:46:02.425000+00:00|原身份只读|
|6|old-stats-SYSTEM|2026-11-02T08:45:11.254000+00:00|原身份只读|

本轮H10起点Oct17 16:20:38.287378UTC、O51起点Oct17 16:29:48.470834UTC，各加604800秒；O续接不改原起点。原文0600/目录0700，所有同批含原文派生同期，safe后缀不豁免。H/O共61实际CAPTURED、0未创建/待核，不复制原文到仓库；公开文件仅安全聚合与hash。本轮0云写/UI/模型/运行部署。用户导出/现役PITR/必要恢复、已有完整ZIP/纯源码/安全聚合保留；文件移除非安全擦盘。

下一Oct20 14:32:29.705948UTC告警341要另建scope/工具双审/主独准备，到期公告/精确hash身份/逐文件删除/独审。计划把原zerde heartbeat改为阿拉木图19:05（14:05UTC），距期限1649.705948秒；日程不保证设备准时，实际更新以本地原heartbeat回执为准。之后再为Oct21及两个Oct24时点独立安排，不提前删除、不复用旧label。旧snapshot已经删除不得重建，旧整包许可不能沿用。

## 交付边界

task_manifest唯一逐工单状态：只更新Z10/Z11/Z15/Z16事实，其余16对象与20状态保持14OPEN/6CLOSED，EpicOPEN。F5 strictFAIL/2x503、费用UNKNOWN、媒体/故障恢复等独立缺口不以本轮替代。工具草稿/harness修订和实际row_epoch失败完整留证，不宣称首次无问题。GitHub文档同步的实际结果另看本地completion/docs-release和独立回执；此源证据时点文档发布PENDING不改写。
