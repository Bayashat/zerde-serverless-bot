## 2026-10-16：四群已发布，writer 原文 1426 份到期责任已履行

Memory V2 四个生产群保持 RELEASED_OBSERVING；dev 学习/回答/定点遗忘/删除后查询及生产激活独审已完成，第四群 News/Quiz/周榜配置已交付。自然 0/50 有据、0/20 未知、起点未建立、production_ready=false；Oct17、Oct21 及之后每周有限观察，首次正常定时投递仍待观察。运行包仍 Bot/Memory PR257、Operations PR263，身份 PR251。开放工单数不表示首发未启用。

原 ledger 的 1426 个完整路径已逐项移除并独立 fresh 核不存在；95425 保留文件（含 45 完整 ZIP）hash/身份、27812 目录原身份/模式及 96851→95425 库存保持。2852 条 intent/result、公告和五 hash 一致，apply/journal 两侧 unlink_returned/absent 严格 True。原期限 2026-10-16 18:48:47.827167UTC 不变；实际首末 unlink 2026-10-16T18:49:13.441939+00:00 / 2026-10-16T18:49:13.995025+00:00，真实晚 25.614772 至 26.167858 秒，原因 UNKNOWN。原 0700/0755/0777 目录分别 13780/14020/12，非全部 cache；25 非目标 private 行政历史按 scope 保留。原失败、UNKNOWN、ledger 和历史报告不改。文件移除非安全擦盘或所有云副本消失；本地清理 0 云/UI/模型/新原文/运行部署，37 在线退役数不增。Due20261016A、Apply20261016A、独立 verify 均结束不可重跑；原 snapshot 不复制、延长或重建。

剩余 5 项原精确 UTC 责任：Oct17 16:20:38 旧 memory PITR；Oct20 14:32:29.705948 告警 341；Oct21 13:10:50.198516 首发最终 527；Nov1 11:46:02.425 旧 memory SYSTEM；Nov2 08:45:11.254 旧 stats SYSTEM。原身份、期限及用户导出/现役 PITR/必要恢复保护保持。20 任务 14 OPEN/6 CLOSED、Epic OPEN。计划将原 heartbeat 调整为每日 Almaty 21:05=16:05UTC，覆盖 Oct17 PITR 前 938 秒；实际设置以 automation 回执为准。逐批再安排下一期限前不超过 60 分钟唤醒，不保证设备准时执行。

[完成证据](evidence/2026-10-16-writer-raw-expiry/completion.safe.json)、[独立不存在](evidence/2026-10-16-writer-raw-expiry/completion-independent.safe.json)、[副本台账](RETAINED_COPIES.md)、[首发进度](LAUNCH_PROGRESS.md)。完整前阶段见[PR272 固定基线](https://github.com/Bayashat/zerde-serverless-bot/blob/0589e61732c6d131b64ee92a67efae1c4cd12646/docs/goals/zerdebot-memory-v2/PLAN.md)。

## 以下为此前冻结阶段，不作当前首发顺序、现场许可或重跑指令

# Shared quota writer 1426份原文到期清理契约

本批当前仅PREPARED_NOT_DELETED。原目录`2026-10-09-shared-quota-writer`，原账本`release-raw-retention.safe.json` SHA `1fbda1fcba166f9ed270e2c658460d86c972bb99b344f45fc024cf64a527ac49`；首次2026-10-09 18:48:47.827167UTC，七日期限2026-10-16 18:48:47.827167UTC（epoch1792176527.827167）不变。严格按原files数组1426个CAPTURED完整路径原顺序，不按后缀/目录/basename/旧槽数删除。

本地完整scope `/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-10-16-writer-raw-expiry/scope.safe.json` SHA `9066fbf3ca1ba7e00403478801a7e6927c81f4d648ce1e26cf3a7890a2c8c48c`，1426目标、95425保护、27812目录、96851文件。原文0600，43个目标祖先目录0700；原构建/依赖0755和12个0777资产根逐路径身份保持，不chmod。45完整ZIP只hash不解包；完整源码、原ledger/安全聚合、失败记录、纯合成probe、25个已核来源行政/工单private历史保留。4automation来源由原创建调用和exit0证明，21issue preimage由原publisher源码证明；不以private后缀决定删除，也不宣称private历史无敏感内容。

95425保护全部fresh hash/身份检查；其中64429另与29个安全来源构建的历史hash映射比较，余30996仅本次fresh基线。候选assembly未套用canonical的依赖pyc旧hash。原explorer第一版映射说明有误，新v2更正且旧稿保全；scope builder主harness首版macOS /var路径别名误停也保留，正式源scope入口未因此执行。准备聚合初审的builder计数/来源/权限/时间链及失败回执缺口已修正后双审，V1/V2未执行草稿保全，不宣称首次无问题。安全来源和当前scope并非原文副本，未复制/延长原snapshot。

主inspect Prep20261015A及独立fresh O_NOFOLLOW/lstat/fstat/流式hash、前后完整库存已结束。工具正确性/维护PRE绑定PLAN/scope/两工具；scope生成器另双PRE绑定分类来源。准备0删除/云/UI/模型/新业务原文或期限。公告、apply、verify_absence未创建或执行；顺序读取非全局事务。

到期当轮先核无并行UI/发布/删除，读实际回执，新唯一inspect，精确公告scope原序1426目标、95425保护、27812目录、待核身份及其它五期限。notice真实announced_targets/deadline_epoch/scope_sha256/announced_at；每项unlink intent距公告0..3600秒。未到期不调用apply试探，早到每次<=60秒等待。工具内部全局/批锁，不套重复外锁。

原hash/模式/身份/全库存保持，期限到达后唯一apply。前后整树检查，逐目标检查全部祖先及父目录fd，逐项fsync intent/unlink/result，预期2852条journal。独立核apply/journal两侧unlink_returned和absent严格True、五hash/时序/目标原序，再fresh不存在与所有保留hash/目录/库存。任何失败或未知保全partial，另窄独审续接，绝不重apply或恢复原文；实际延迟按真实时间记录，不明原因UNKNOWN。

六项原期限完整保留；用户导出、现役PITR/必要恢复、资产审计模板保持，文件移除非安全擦盘或所有云副本消失，37在线退役数不增。四群已RELEASED_OBSERVING；本次文档merge非运行构建，旧reader/media许可不因源码相同恢复。

[主准备](evidence/2026-10-16-writer-raw-expiry/preparation.safe.json)；[独立准备](evidence/2026-10-16-writer-raw-expiry/independent.safe.json)；[台账](RETAINED_COPIES.md)。
