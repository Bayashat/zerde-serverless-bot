# 正常调度费用恢复有限读回

本批是PR280部署后的新时点证据。主ReadProgress20261020A与独ReadProgressIndependent20261020A均已完成，不重跑；原严格OBSERVED_PENDING结果保留。当前只证明历史缺块补齐和AWS估算恢复，完整原五owner/模型headroom与媒体发送许可仍须独立核验。

## Oct20：历史费用缺块已补齐，AWS估算恢复为已核验

PR280部署后的新主独各六次只读一致：39 DAY行，38完整、0缺席、1当前块短覆盖、0错inventory；此前6个缺失历史块已补齐。AWS为`ESTIMATE_VERIFIED / OBSERVED_GROSS_ESTIMATE`、paused=false，估算5,321,387 microUSD。观察时间07:08:30UTC，覆盖至06:50:00UTC，有效至10:08:30UTC，均为当时证据，不是持续许可或实付账单。

本次严格检查请求覆盖到07:05UTC，当前块差900秒，所以两份原结果仍`OBSERVED_PENDING`。原运行AWS门允许3小时内的有效覆盖，该差距不等于历史缺块或AWS门仍失败；原结果不改写。完整五owner模型预算和当前包媒体绑定仍未核验，不能据这12读发送媒体。运行源仍PR280 `fd53b30b2d07704f091e0a407375d254e5705819`，本轮没有部署、云写、模型或Telegram操作。

实际独立原响应POST通过；12份原文统一到期 **2026-10-27 07:23:59.115275UTC**，总计十三项独立副本职责。下一优先离线完成当前包与原owner/reader/媒体工具绑定，再按新的直接人类独占窗口和完整原预算检查继续；不为移动计量水位反复六读。今日告警341与明日首发527期限保持。四群已启用、自然质量仍待发布后观察，20任务14OPEN/6CLOSED与EpicOPEN不变。[本批契约](COST_RECOVERY_FOLLOWUP.md)；[副本职责](RETAINED_COPIES.md)。


实际回执：本地 `/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-10-20-cost-recovery-followup`。主独12AWS只读/0写、0UI/模型/预算预留/运行发布，顺序读取非跨行事务；CI既有OIDC/CDK只读另计。独立审直接核12原响应、身份/hash/权限/固定参数、两账本前缀及原Q snapshot期限，不只审主摘要。

- [最终聚合](evidence/2026-10-20-cost-recovery-followup/final.safe.json)，SHA `bda5c2fe1d063c089aa8130479cc4645eabb70817303ebe7c87bf40cfe185d88`。
- [最终独立](evidence/2026-10-20-cost-recovery-followup/final-independent.safe.json)，SHA `3513a6453dc125dafb03915317193736fd49140023173a8b72046fc10d0d7a30`。
- [原响应独审](evidence/2026-10-20-cost-recovery-followup/independent-post.safe.json)，SHA `1536ab5ba6cfc255b38c86d28e885e41b1750a7d51ac3e8b7d9ea53b51d08ce8`。

新原文期限独立于旧Q；所有已结束once冻结，原工具草稿端点/HTTP类型/期限/失败停止修订、harness和路径误停保全，不宣称首次无问题。此次没有运行代码变更，文档main不当新运行构建。原两环境已部署实包、四群启用、自然0/50有据0/20未知、起点null和production_ready=false含义不变。
