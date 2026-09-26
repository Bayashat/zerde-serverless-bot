# Z20 旧资源退役执行契约（S4）

执行依赖：PR224的dev/prod实际代码包、配置和保护状态读回完成。状态来源仍是task_manifest；本文件不是新的任务计数或已删除证明。遵循FINISH_EXECUTION和RETIREMENT_INVENTORY，在任何新功能、新群或生产记忆启用前完成清理。

## 范围与所有权

主代理负责infra、workflow、当前配置、vector入口和必要测试的集成；独立审阅者核对模板、实际变更集和云端结果。Memory V2事实、来源、控制及费用owner不变。删除前向用户列出本批精确资源与保留项。

每环境移除14个既有声明：旧memory表、vector queue/DLQ、vector bucket/index、indexer函数/role/policy/日志/事件映射及4个专属告警。精确logical/physical ID由当前栈现场生成manifest，并与已告知清单逐项对应。Bot按45个旧环境项白名单删除现场实际存在的子集及对应IAM，不为凑数补回此前省略项；Operations告警名单只减少4个vector名称。删除indexer入口和专用router，保留混合主队列的旧schema拒绝协议。

现役函数集合固定为Bot、News、Quiz、Operations、MemoryV2Worker；现役表固定为dev/prod的stats、Quiz、MemoryV2共6张。主队列/V2/Operations队列、层、API、资产桶及业务规则继续保留。active环境从6函数/3映射/22告警变为5/2/18；idle-dev仍遵循原按需停用配置。

**费用清单不变。** 原MEMORY_COST_INVENTORY只包含两环境的4个Bot/Worker、2张V2表、4条V2队列及10个增量告警，不包含vector。不得改变inventory版本、metering_started_at、价格/预算策略、DAY或UNKNOWN历史，不建立新预算owner。

## 顺序、证据和失败处理

1. 在合并前暂停自动deploy workflow，全分页确认没有非终态部署；保持到两环境删除及独审完成再恢复并读回。避免合并自动触发未经门禁的dev Delete。在最新已发布main实施依赖解除；同步配置、workflow/examples及五函数打包校验。保留现役业务测试和旧任务拒绝测试。新合成dev/prod模板逐对象比较；只允许精确Remove、Bot旧env/IAM减少、Operations告警名单减少和Bot/Worker代码更新，其他变化必须解释和审阅。
2. 执行前再次完整强一致读取两旧表，核对dev0/prod3精确键、字段类型与整行hash；只允许pk/sk/memory_enabled/agent_enabled/updated_at，没有style。发现额外数据或有效设置立即阻止旧死开关删除路径，先保护其真实语义。不得迁移旧开关来启用V2。
3. 刷新所有权、alias/version、映射、队列上下游/redrive、向量索引/向量全量枚举及日志保留职责。vector index/bucket完整枚举必须与批准身份集合相等，各目标向量均为0；额外index、非零或未知结果阻止删除。专用queue的可见/在途/延迟数必须均为0；不用Receive或Purge证明空，也不清混合主队列。保持旧写入Deny直至对应资源删除或精确不存在读回。
4. 独审实际changeset后dev先执行。dev的Delete会真正删除资源，前置必须在执行前通过。prod的6个Retain对象移出模板后仍存在，按同一manifest另做精确物理删除，index先于bucket；只解除目标旧表的删除保护。每项持久intent/结果；未知响应先只读对账，不自动重发。
5. 两环境五个实际包、配置、层、6张现役表身份/保护、控制/epoch、规则和预算owner前后核对。独立逐项确认退役资源不存在；CFN完成不能代替物理删除完成。异常保留部分状态，正常功能仅回退无长期记忆显式问答，不恢复旧算法。

## 不并入本批的对象

更早的zerde-prod-bot-stats、旧updates queue/DLQ和4个孤立日志组须另做消费者和内容复查，不能用此栈内白名单顺手删除。外部消费者未明的旧SSM参数、现役密钥、用户Telegram导出、其他项目及整个栈都不删。

源表删除与备份副本是不同验收。删除时记录可能新增/保留的服务恢复副本及截止日期；不把源表不存在说成全部物理抹除。Z10既有PITR复查2026-10-17 16:20:38UTC和其他副本职责保留，已经到期移除的本地密文与key不重建。

## 完成和同步

新代码完整测试、真实五函数ARM导入、当前模板/变更集独审、逐目标云删除与不存在读回均通过后，才将对应清单项标完成。R2整体还需要处理更早候选和未知消费者；R3业务/实际费用验收及R4自然使用门槛分别保留。每次交付同步task_manifest、TASKS、HANDOFF、EVIDENCE、Z20/Z04/Epic和现有automation，不把本计划当已执行证据。
