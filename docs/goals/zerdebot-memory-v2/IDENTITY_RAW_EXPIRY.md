> 以下为PR270配置1030清理完成时的历史快照；1030已履行，当前剩余期限见[副本台账](RETAINED_COPIES.md)。原历史中的提及Reply85待到期已由本次独立回执闭合。

## 2026-10-14：四群已发布，配置原文1030份到期责任已履行

Memory V2四个生产群保持 **RELEASED_OBSERVING**；dev学习/回答/定点遗忘/删除后查询与生产激活独审已完成，第四群News/Quiz/周榜配置已交付。运行包仍Bot/Memory257、Operations263，身份251。自然0/50有据、0/20未知、起点未建立、production_ready=false；Oct17、Oct21及之后每周有限观察，首次正常定时投递尚待观察。开放工单数不代表首发未启用。

配置发布原文1030个当前完整路径已逐项移除并独立fresh核不存在；其中95迁移旧失败与后来成功路径均按原ledger处理，不按旧路径或basename推断。310保留文件（含24完整ZIP）的哈希/身份、37目录及1340→310库存保持；2060条intent/result、公告和五hash一致，apply/journal两侧unlink_returned与absent严格True。原期限21:48:46.021161UTC保持；首末unlink 2026-10-14T21:48:46.697077+00:00 至 2026-10-14T21:48:50.604921+00:00，真实晚0.675916至4.583760秒，原因UNKNOWN。原失败、ledger及列明0755模式保持，pre-controls不是cache。文件移除非安全擦盘/所有云副本消失；0云/UI/模型/新原文/运行部署，37在线退役数不增。Due20261014B/Apply20261014B/独立verify均已结束不可重跑。较早公开文本128亦已履行，原回执不改。

当前剩余7项精确UTC职责：Oct15 08:17:52.186798提及Reply85；Oct16 18:48:47.827167 writer1426；Oct17 16:20:38旧memory PITR；Oct20 14:32:29.705948告警341；Oct21 13:10:50.198516首发527；Nov1 11:46:02.425旧memory SYSTEM；Nov2 08:45:11.254旧stats SYSTEM。原身份、期限与保护保持，20任务14OPEN/6CLOSED、EpicOPEN。下次计划07:35UTC唤醒覆盖Oct15期限；未来逐批调整为距下一期限不超过60分钟，不保证设备必然准时唤醒。

[本批完成证据](evidence/2026-10-14-identity-raw-expiry/completion.safe.json)、[独立不存在](evidence/2026-10-14-identity-raw-expiry/completion-independent.safe.json)、[副本台账](RETAINED_COPIES.md)、[首发进度](LAUNCH_PROGRESS.md)。完整前阶段见[PR269摘要](https://github.com/Bayashat/zerde-serverless-bot/blob/30752b6755f3461ffb6260c4202b0c127966a5ac/docs/goals/zerdebot-memory-v2/PLAN.md)。

## 以下为准备时冻结契约；实际完成以上方回执为准，不重跑

# 1030 份原文到期清理契约

当前仅准备完成，apply、独立不存在核验和删除公告均未执行。主inspect唯一label Prep20261013A已经结束不可重用。原期限 **2026-10-14T21:48:46.021161+00:00**（epoch 1792014526.021161），源目录2026-10-08-dev-bot-identity-fix；目录日期不改实际起点2026-10-07T21:48:46.021161+00:00。

原ledger `release-raw-retention.safe.json` SHA256 `a23b0b8eff40e11356aaad08902642ff8570be816168090a9975cc03a04cd6ea` 固定1030个CAPTURED路径原顺序。scope SHA256 `af65b8f3388c6bd9747ab7f79bca70e01ffd3da1caa6fc6b8e6ea3e3e9ef067e`；本地完整删/保留/目录清单 `/Users/bayashat/.local/share/zerde-memory-v2-acceptance/2026-10-14-identity-raw-expiry/scope.safe.json`。实际全库存1340文件；310文件哈希/原身份和37目录模式/身份固定。目标0600、原文父目录0700，原非0700目录按精确路径保持：N的__pycache__为0755；G的__pycache__、operators/__pycache__和pre-controls为0755（pre-controls不是cache）。独立fresh无跟随打开/hash/lstat重新核对，并非只读主结果。

G批1030同时包括95迁移失败和后续成功路径，按当前完整路径处理，不按previous_path或basename合并，也不能套用U晚次成功同名保留规则。24个完整ZIP、纯源码、安全聚合、原账本和asset审计模板保留。N批原鉴权/普通文本及ask有限通过、mention真实FAIL、UI_STOP和审计源晚登记偏差不改；登记含原文派生已在128内。非目标private历史按来源核对，不因后缀删除。

到期当轮先无占用和新唯一inspect，按scope原顺序精确公告目标/保留/待核及执行时其余未履行期限。保存真实announced_at/announced_targets/原deadline_epoch/scope_sha256，每项unlink intent距公告<=3600秒。未到期只预检后每次<=60秒等到期，不apply试探、不故意拖晚。实际原hash/文件与全部目录身份/库存保持后，在内置全局锁和批锁下唯一apply，再由独立代理首次执行verify_absence。预期2060条fsync intent/result，apply与journal的unlink_returned/absent各自必须严格True，公告和五hash时间链必须一致。

任何未知/身份或hash变化/占用/失败即停并保全partial，新窄续接需独审，不能重apply/重建原文。成功unlink后即记事实，不因后续close/journal失败抹去已删结果。文件移除非安全擦盘或所有云副本消失。准备0云/UI/模型/删除/新业务原文；后续CI基础设施只读另计。原八项期限不变，两个Oct14时点不合并。

[主准备证据](evidence/2026-10-14-identity-raw-expiry/preparation.safe.json)；[独立fresh准备](evidence/2026-10-14-identity-raw-expiry/independent.safe.json)；[完整副本台账](RETAINED_COPIES.md)。本批工具是新冻结副本，不调用旧once或建立共享可变工具owner。
