# Memory V2 首发已完成，进入生产观察

2026-10-14 17:14:07.647307 UTC（阿拉木图22:14），四个已授权生产群逐群条件激活完成；17:16:41.027804 UTC独立新鲜读回通过。状态 **RELEASED_OBSERVING**。PR268文档已合并，CI三job与独立核验通过；merge517cebfa800e56aabbc1e9a2b5de7bf3059c0fe9，无额外部署。

|范围|实际结果|后续|
|---|---|---|
|核心回归|554通过；全套2474通过/1旧权限fixture失败，同节点umask022复核通过|原失败保留，无需重跑全套|
|dev真实链路|来源2417学习；2418→2419来源回答；原生Reply2420定点遗忘；2422→2423删除后不再引用，全部PASS|已结束，不重发/重测这些输入|
|生产Memory V2|四群ACTIVE、learning=true，初始revision1与独立epoch；主24 API含4条件事务，独立6只读|正常真实使用与异常观察|
|第四群定时业务|News、工作日Quiz、周榜配置及独立读回通过|首次正常定时投递尚未观察|
|完整自然质量|0/50有据、0/20未知、起点未建立|发布后第3天Oct17与每周（首次Oct21）观察|

Memory范围：中文 -1002211083217；哈萨克语 -1001244628965、-1001450935528、-1004490324695。原CONTROL缺席时由唯一MemoryRepository条件创建，没有覆盖旧epoch或手写预算。运行Bot/Memory仍PR257、Operations PR263、身份配置PR251；本次无Lambda代码包更新。生产真实使用可以合法推进revision，不将初始revision1当永久值。

第四群 -1004490324695：News每天09:00，Quiz周一至周五13:00，周榜周五18:00（阿拉木图UTC+5）。原其他目标和规则保持，中文News仍DISABLED；未手动调用/补发。此前SchedulePrepareA严格门禁失败与唯一ExecuteB完成原样保留。

dev来源清理于16:59:01UTC达到DONE，9行移除，原RAW/HEAD及该来源FACT缺席，OBS保留最小删除墓碑；删除后回答明确没有可支持的本人公开信息，单SENT、source_refs空、lease释放。只核当前操作者interests前缀恢复原基线，不推所有用户或所有画像域。主代理操作原生UI，独审检查保存记录及另22次fresh只读；数字消息ID来自持久记录，没有取得原生精确链接。顺序读取不是全局事务。Window A上下文STOP、Erase1/2尚DELETING、Erase3采集在B窗口内但评分已过期拒绝、C窗口续接及所有草稿失败均保留；没有重发来源、问题或遗忘。

20任务仍14OPEN/6CLOSED，Epic OPEN。这些开放项包括发布后质量、媒体/频道有限缺口、独立业务恢复、费用UNKNOWN及副本职责，不再作为首发等待列表。production_ready=false仍指完整自然质量；启用与自然验收分开。不会用受控测试、空群日历或自动消息凑自然样本。

首发最终527CAPTURED/0NOT_CREATED，原Oct21 13:10:50.198516UTC期限固定。公开文本128、配置1030及提及Reply85已分别删除并独审；本批85删除/103保留/6目录保持。详见[副本台账](RETAINED_COPIES.md)。剩余六项未履行UTC期限分别为：

|期限UTC|责任|
|---|---|
|Oct16 18:48:47.827167|shared-quota-writer原文1426|
|Oct17 16:20:38|旧memory PITR精确只读|
|Oct20 14:32:29.705948|告警诊断原文341|
|Oct21 13:10:50.198516|本次首发最终527实际ledger|
|Nov1 11:46:02.425|旧memory SYSTEM精确只读|
|Nov2 08:45:11.254|旧stats SYSTEM精确只读|

每批沿精确原ledger/hash/身份与原期限，单独新PRE/公告/到期删除/独立不存在；已履行的公开128、配置1030和提及Reply85均不可重删，不能提前删除或重建旧原文。用户导出、现役PITR、必要恢复和安全聚合保留；文件移除不是安全擦盘。第3天/每周检查采取有限只读和实际自然证据；发现跨群、身份、敏感泄露、删后复活或误删，依原公开停止入口暂停对应群并保留证据。

[完整安全聚合](evidence/2026-10-14-memory-v2-launch/completion/final.safe.json)、[dev完整独审](evidence/2026-10-14-memory-v2-launch/completion/dev-independent.safe.json)、[四群实际独审](evidence/2026-10-14-memory-v2-launch/completion/production-activation-independent.safe.json)、[定时配置独审](evidence/2026-10-14-memory-v2-launch/completion/schedule-final-independent.safe.json)。

此前完整阶段与失败记录固定于[PR267发布前进度](https://github.com/Bayashat/zerde-serverless-bot/blob/cbcd8b1126d95577eeb4e6c9b2778b5c32fb27c1/docs/goals/zerdebot-memory-v2/LAUNCH_PROGRESS.md)，所有已结束once不可重跑。
