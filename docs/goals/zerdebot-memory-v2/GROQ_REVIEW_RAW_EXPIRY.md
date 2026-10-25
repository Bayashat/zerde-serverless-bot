# Oct26 Groq 审核发布原文到期准备

实际准备已完成，尚未删除。原 ledger SHA eccbecaac4db0bbdc7b9513dbe411f669410c74b75529c2aa936bce9af038318 的 418 CAPTURED 路径原序是唯一目标，含失败发布响应及两个不带 private 后缀的模板。原起点 2026-10-19 20:29:05.508343 UTC；原期限 2026-10-26 20:29:05.508343 UTC / epoch 1793046545.508343 保持。

| 目标 | 保留 regular | 目录 | 完整 regular 库存 | 链接 | 保留 ZIP |
| --- | --- | --- | --- | --- | --- |
| 418 | 31569 | 8960 | 31987 | 0 | 39 |

目录 5549 个0700、3411 个0755；常规文件31951个0600、36个0644逐项保持，不 chmod。目标祖先均0700，无非目标 private 文件。563保护文件有历史hash来源，31006只fresh基线；历史来源中561具有safe回执内精确指针、4具有原handoff根hash锚，两类交集2、并集563。39 ZIP均有明确历史完整包hash。原explorer/provenance报告冻结，新binding只规范字段和绝对路径；来源分类早期误将两类互斥的草稿保全。

原ledger记录hash/size/dev/ino/mode，没有mtime或nlink。本轮先核原hash与身份，再冻结明确标注FRESH_PREPARATION_BASELINE_NOT_ORIGINAL_LEDGER的mtime和当前nlink；主inspect、独立fresh及未来unlink前保持该新基线，不声称原创建以来mtime或inode一直未变。O_NOFOLLOW/lstat/fstat流式读取、全库存前后及所有保护hash/目录身份核对通过；不解析或复制原文，顺序读取非原子快照。

正式scope构建、主Prep20261025B inspect/seal、独立fresh已结束，不能重跑。准备工具时间门在正式执行前补齐库存扫描与保存前后检查；未执行旧源码、来源字段adapter修订及TEMP夹具路径/umask等失败保留，不宣称首次无问题。离线控制仅TEMP，不是业务验收。

到期另唯一Due20261026B inspect，按scope原序精确公告全部418目标、31569保护、8960目录、0link、待核和当时其他职责；真实notice绑定原deadline/scope/announced_at，每intent距公告0..3600秒。原hash/身份/fresh mtime/全库存保持且到期才唯一Apply20261026B，836条intent+result journal；apply与journal两侧unlink_returned/absent严格True后独立fresh不存在。未到期不试探apply，不重apply或重建原文；未知保全partial另窄合同。普通unlink非安全擦盘或全部云副本消失。

本批0删除/云运行调用/UI/模型/预算/新原文/新期限/运行部署/自然增量，CI既有OIDC/CDK只读另计。剩余16项原UTC责任不合并延期；H10/O51及之前履行批次不再执行。Nov1/2 SYSTEM仅按原身份到期只读。四群RELEASED_OBSERVING、自然0/50有据0/20未知/起点null保持。普通ask真实有用性、媒体/恢复/人工审核/费用独立缺口仍开放，无新Telegram窗口。

同一zerde每日阿拉木图01:00（前日UTC20:00）保持，Oct26 20:00覆盖本原期限前1745.508343秒；日程不保证准时。履行后必须按下一Oct26 23:52及Oct27各原时点前60分钟内重排，不能机械沿当前日程处理全部，也不复制或删除自动任务。

- B：[主准备](evidence/2026-10-26-groq-review-raw-expiry/B-preparation.safe.json)、[独立fresh](evidence/2026-10-26-groq-review-raw-expiry/B-independent.safe.json)、[正确性PRE](evidence/2026-10-26-groq-review-raw-expiry/B-tool-pre.safe.json)、[维护PRE](evidence/2026-10-26-groq-review-raw-expiry/B-maintenance-pre.safe.json)。scope SHA `194d626f7a144e1cc80b2269bbadeffdf253dc50633bce3d14fe2652a3ed810f`。

[共同实际聚合](evidence/2026-10-26-groq-review-raw-expiry/final.safe.json)、[原16项职责](RETAINED_COPIES.md)。
