# Memory V2 加速首发实际进度

本页记录 2026-10-14 本次实际动作；后续文档发布与 workflow 恢复以外部 docs-release/独审回执为准。

|范围|实际状态|剩余动作|
|---|---|---|
|离线安全回归|554核心通过；全套2474通过、1旧fixture失败，同节点umask022复核通过|没有产品缺陷证据，不重复全套|
|dev真实学习与来源回答|新来源2417；问题2418→回答2419；有效FACT、持久SENT、单回答、lease释放及可见语义通过|遗忘与删除后查询尚未发送|
|第四群News/Quiz/周榜|AWS配置、生产环境变量与独立新鲜读回通过|按原日程正常运行，首次正常投递尚未观察|
|四生产群Memory V2|直接用户授权，精确工具及双审准备完成|dev遗忘验证后逐群条件激活与独立读回|
|长期质量|自然0/50有据、0/20未知；起点未建立|发布后第3天及每周观察，不作首发等待门槛|

Memory目标：中文 -1002211083217，哈萨克语 -1001244628965、-1001450935528、-1004490324695。只使用原MemoryRepository初次条件激活，不重置既有epoch/预算，不恢复旧自动社交或历史导入。

第四群 -1004490324695 的 News 每天09:00、Quiz周一至周五13:00、周榜周五18:00，以上为阿拉木图时间（UTC+5）。原其他群目标/规则状态/日程保持，中文News保持DISABLED；未手动调用或补发。production环境NEWS_CHATS_KK与QUIZ_CHATS_KK已分别设置完整目标，repo原值不变，dev因此保持。现有workflow使用production环境变量。

首轮SchedulePrepareA上传并创建候选后，严格范围门禁发现额外IAM摘要和描述表示差异，未Execute。IAM权限语义变化未证明，原模板键顺序变化及CF/Events两条描述表示差异均保留。新B保持原键顺序、精确恢复原Events描述，changeset严格只有三个Targets变化；唯一ExecuteB成功，UPDATE_COMPLETE/EXECUTE_COMPLETE，五Lambda配置及栈保护主读回通过。新的独立8AWS+3GitHub只读再次核完整模板、三规则与目标、两production变量；没有重复下载五函数包，正常定时投递仍未观察。所有已结束入口不可重跑。

Telegram Window A在遗忘发送之前发生上下文变化，原因UNKNOWN；旧forget意图未发送，没有向其它群发测试。新窗口续接工具已双审，只能收到新的直接“现在独占”回复后登记真实起止、核账号/唯一dev群/空草稿，再fresh检查本次来源后发送一次定点遗忘及删除后查询。旧UI_STOP和原测试失败保持，不使用旧窗口或旧草稿。

运行Bot/Memory仍PR257、Operations PR263、身份配置PR251；本次三定时目标更新没有新Lambda部署。四群Memory尚未启用、完整dev首发验收尚未PASS。20任务14OPEN/6CLOSED及Epic OPEN不等于尚需14项才能发布；其中长期观察/独立业务恢复/费用/副本继续单列。

当前账本246CAPTURED为阶段数量，后续同批原文加入同一期限2026-10-21 13:10:50.198516UTC，不延长。原八项期限和今晚两批清理保持；文件删除不是安全擦盘，用户导出/现役PITR/必要恢复保留。[台账](RETAINED_COPIES.md)。

[阶段安全聚合](evidence/2026-10-14-memory-v2-launch/progress.safe.json)、[dev答案独审](evidence/2026-10-14-memory-v2-launch/dev-answer-independent.safe.json)、[AWS部署读回](evidence/2026-10-14-memory-v2-launch/SchedulePostB.safe.json)、[变量同步](evidence/2026-10-14-memory-v2-launch/ScheduleSyncA.safe.json)、[独立新鲜读回](evidence/2026-10-14-memory-v2-launch/ScheduleIndependentA.safe.json)。

[调度最终独立链](evidence/2026-10-14-memory-v2-launch/schedule-final-independent.safe.json)已核123份原始记录；其范围限配置与变量，workflow恢复另见实际文档发布回执。

首发激活窄合同明确只要求目标CONTROL不存在；现有显式ASK短期行可以保留，不扫描或清空整群分区。该澄清覆盖冻结首发计划第7条中“无旧V2工作/事实”的过宽表述，不授权覆盖既有CONTROL或数据。
