# Memory V2 最近话题贡献（Z08 派生服务）

此 slice 将已有 `aggregate_trends` 的固定技术词表接到唯一 `TrendService`，提供可恢复的每日摄取扫描与可核验的群话题读取。没有调用模型，没有新增个人兴趣/关系/人格推断，也没有独立群事实写入路径。群规则/决定仍由 FactWriter 的管理员确认接口拥有。

## 数据归属与失效

同一独立 V2 表、同一 `CHAT#<chat_id>` 分区，每个源只有一个 `TREND#<20位补零 message_id>` 派生行。包含固定 `kind=TREND_CONTRIBUTION`、`revision`、`epoch`、`source_ref`、`source_id`、`actor_user_id`、`subject_generation`、规范正文 hash、原始时间、词表版本和 topic labels，不含原文或自由生成的事实文本。

`contribute(chat_id, SourceRef)` 从 `MemoryRepository.source_snapshot(learning=False)` 读取已经准入的 RAW/HEAD/OBSERVATION/subject/control，纯函数分类，再在同一个原生 DynamoDB 事务中复验这些版本并 CAS 本源贡献。新编辑可以替换旧贡献；旧版本或旧 epoch 任务不能写回当前贡献。重投不会重复累计消息数，只能重写同一个源的派生行。学习暂停期间保留当前安全来源的读取及确定性分类；是否暂停新增 AWS 工作由公共运维预算开关控制。

贡献的 `expires_at` 和 TTL 均为 **原始发送时间 + 7 天**，读取检查逻辑到期，不等待 DynamoDB TTL。编辑不会延长窗口。引用段在词频分类前排除。同一条消息对同一话题计一次，参与人数按真实个人 ID 去重；这些计数不能回写某个人的 `tech_stack/interests`。

`source_id/source_ref/actor_user_id` 直接兼容 Z09 `MemoryLifecycle._belongs` 的派生归属规则。subject/source/group forget 会精确清理对应贡献；删除无需另外依赖 vector 或外部 cleaner。旧实体即使暂时未物理删除，也会因源/subject/control fence 不匹配而立即不可读。`TREND_REFRESH` 只保存本群分页游标和扫描时间，没有个人正文；群删除时由通用生命周期清理。

## 接口与覆盖率

```python
service = TrendService(memory_repo)
service.contribute(chat_id, source_ref)
progress = service.refresh(chat_id, max_pages=2, page_size=20, runtime_seconds=20)
view = service.read(chat_id, max_pages=2, page_size=20, max_sources=20)
service.validate_snapshot(view)
```

`refresh` 对 HEAD 强读分页。每页贡献完成后，持久 CAS `TREND_REFRESH` 游标；DynamoDB/事务错误向上传播，不当作 source 不存在，不推进失败页。重放该页不会累加重复计数。到达本次时间限制会保留原页游标，返回 `page_restarted/pending`；下一次从持久游标继续。返回 `scanned/updated/obsolete/pages/pending`，不能把一页成功说成全群完成。

`read` 强读有界贡献页，默认最多 20 个有效来源，并优先选择最近的 Telegram message_id。每条来源都再次核对 canonical RAW/HEAD/OBSERVATION/control/subject；过期、删除、optout、旧 epoch、旧词表、伪造作者或 topic labels 都排除。返回：

- `snapshot`: 既有 `TrendSnapshot`，包括 7 天窗口、topic 消息数、参与人数、每日分布。
- `source_refs`, `evidence_authors`, `proofs`, `control_revision`: 精确来源与主体版本，供公共回答 lease 绑定。
- `coverage`: scanned/accepted/obsolete、truncated、续读 cursor、贡献扫描是否结束、最近完整 HEAD 遍历的起止时间和是否有未完成刷新。

`scope=validated_contributions`，`newer_sources_may_be_missing=True` 明确表示结果限于已产生贡献并通过当前验证的消息。即使 `contribution_scan_complete=True`，也不表示所有原始消息都已准入或已刷新。HEAD 分页不是某个时点的原子全库快照，新到/迟到消息可能留待下一轮。没有完成过完整扫描时 `inventory_verified=False`。公共界面必须展示采样/截断和刷新时间，不能将这个最多 20 来源的结果称作完整群统计。若需要更多消息，调用方必须显式分页，并承认多页各自验证时点不同，不能拼接后宣称获得原子全量快照。

## 并发边界与公共接线

`validate_snapshot` 重新读取全部来源和主体，刷新当前时钟检查 7 天到期，再用一次仅包含 ConditionCheck 的原生事务给所有指针建立共同验证时点。最多 20 个来源，因此最坏 81 项检查（control + 20 subjects + 20 HEAD + 20 RAW + 20 OBSERVATION），低于 DynamoDB 100 项事务限制。此操作需要表事务权限并产生 DynamoDB 请求；不能把纯 Python 分类误说成零 AWS 成本。

这仍不能让 Telegram 发送与 DynamoDB 删除原子化。公共发送必须在此验证基础上按 Z09 协议登记/绑定 `source_refs/evidence_authors` 的 answer lease，在发送前复验；forget 确认需等待这些已登记发送完成或到期。当前 slice 不修改公共 answer/lease/runtime 文件，也不声称完成其接线。只有源作者处理器会写贡献，模型不能指定任意作者或跨群 source。

每日 schedule、worker 成功后的可选贡献调用、展示和 lease 扩展由集成负责人统一接入。未部署、未调用真实 AWS/Telegram，实际 Lambda 运行时长、DynamoDB 延迟与群样本覆盖率待 dev/生产证据。测试使用 Moto 的 DynamoDB Resource 原生事务与条件语义模拟，不等同于真实 AWS 验收。
