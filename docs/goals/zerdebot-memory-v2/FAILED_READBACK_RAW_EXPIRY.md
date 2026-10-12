# Oct13晚次失败读回四文件到期清理

目标：履行Z10持有的PR248首次dev主读回失败3份原文及独立STS超时空记录1份责任。原期限2026-10-13 18:26:43.519150UTC（1791916003.519150）不变；独立记录原18:51:50.905062已按既有ledger提前，不能恢复较晚期限。Oct13早次发票3和本晚次分别执行，不合并。

真值：J=验收根2026-10-06-explicit-quota-guard的failed-dev-download-retention.safe.json和failed-independent-dev-retention.safe.json。唯一删除目标为下列迁移后路径，按scope原顺序/hash/identity；原ledger的previous_path不是删除入口：

1. post-main-dev-download-incomplete/responses.private.json
2. post-main-dev-download-incomplete/artifact-responses.private.json
3. post-main-dev-download-incomplete/snapshot.private.json
4. post-independent-dev-sts-timeout/metadata-responses.private.json

第四个文件仅3字节空数组记录，不是AWS响应。本次不生成原始响应、读云、恢复ZIP或旧采集；不按private后缀/目录/槽上限删除。主3目标合计元数据及独1空记录共669748字节。所有目标0600、单硬链接、普通文件且无symlink。

保留scope列明12文件：两失败目录的6个非目标（bot.zip、news.zip、readback/review及两原ledger），J根两份权威迁移ledger，成功轮post-main-dev的responses/artifact-responses/snapshot及post-independent-dev的metadata-responses四个同名路径。目标与成功路径当前不同hash/inode，成功路径必须保持，不能从旧ledger删除。两归档记录仅作不可变hash来源。五目录（J根、两失败、两成功父目录）0700/原device/inode保持，永不删除目录。

完整库存门禁只覆盖两个失败目录现有7+3=10文件，禁止未登记新条目/子目录/链接；其余J源代码、构建树、成功包/源展开放在边界外，不递归、不声称完整J库存核验。16个精确文件（4目标+12保护）及5目录身份固定于scope/PINNED，任何身份/hash/模式变化停止。

主代理顺序实现本计划、scope和两工具；独立正确性/维护PRE与有意义合成控后，主代理新唯一label inspect，独立fresh无跟随hash/lstat核4仍在/12保护/5目录/两个归档完整10库存。该准备0删除/云/UI/模型，不算到期履行。

到期当轮先核主代理/进程/工作树/PR/全局.zerde-release-operation.lock独占；新label inspect不重复准备label。真实公告四路径、12保留/5目录及待核（可链接scope精确清单）。notice字段announced_targets严格scope原顺序、deadline_epoch原值、scope_sha256及真实UTCepoch announced_at；每项unlink intent距公告0至3600秒。未到期不apply试探，早到同轮等每次不超过60秒，实际迟延原样记录。

到期且全量门禁保持，主代理持全局锁运行 `python3 -B expire_raw.py apply <新唯一label>` 一次；本地.operation.lock亦防并行。每个目标再次核固定inode/hash/父目录描述符和到期、新鲜公告；8条fsync逐项intent/result，unlink成功先保存内存已删事实，再close/journal，后续失败不抹掉已知效果。

apply结束后独立代理持全局锁第一次执行 `python3 -B verify_absence.py`。实际lstat四路径不存在、12保护hash/identity与5目录身份保持，两失败目录剩余6文件，8条journal/notice/intent/apply及原ledger全链相同。非安全擦盘、非所有云/外部副本消失或文件系统事务；不改原INCOMPLETE报告，不把成功续接说成首次成功。

任何占用/漂移/过早/过旧公告/未知均停并保全partial；禁止重apply、重建原文、覆盖旧失败。需要续接时另建精确剩余合同与独审。实质交付同步计划/证据/task_manifest/TASKS/HANDOFF/RETAINED_COPIES及相关GitHub正文与automation，准备、执行、独审、文档交付分别记。

任务板：主代理计划/实施串行；正确性与维护代理只审/合成控；PRE后主inspect、独立准备核；到期主apply、独verify；主同步文档，双审、CI、合并与最后独立读回。不并行UI/删除/发布，全部旧once冻结。运行PR257/配置PR251/S reader不变，不执行reader。用户导出/现役PITR与其它期限保护，37在线对象不增。Z10/Epic开放、自然0/50与0/20、production_ready=false保持。

[主准备](evidence/2026-10-13-failed-readback-raw-expiry/preparation.safe.json)；[独立准备](evidence/2026-10-13-failed-readback-raw-expiry/independent.safe.json)。原主报告PENDING由后独审闭合，不改原字节。
