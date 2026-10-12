# Oct13早次账号发票摘要三份原文到期清理

目标是履行 Z10/Z17 的既有三文件人工清理责任，原期限 2026-10-13 08:06:04.659429 UTC（1791878764.659429）不变。此目录名称是责任日期，不表示已到期或已删除；Oct12答案247和Oct13晚次失败4各自独立执行，不合并。

真值来自旧 `2026-10-06-provider-cost-gaps/invoice-retention.safe.json` 与 `invoice-v2/invoice-retention.safe.json`。前者真实开始 08:06:04.659429，后者 08:10:05.475220 仍采用前者更早期限。清理 scope 固定三个相对路径及原 SHA，不能把原11/10调用上限当实际21文件：

1. invoice-raw/001.private.json
2. invoice-v2/invoice-raw/001.private.json
3. invoice-v2/invoice-raw/002.private.json

保留 scope 列明的83文件和7目录：原两ledger/起点、首次端点校验失败、摘要和独审、源码/旧工具、GitHub文档与自动任务历史、原缓存。当前原始库存86文件；所有原文派生仍按原两ledger（目前为空）核查，不能单凭扩展名判断。GitHub工单before和automation私有历史是待核分类，不因private后缀自动删除。核完再允许准备PASS。用户Telegram导出、现役PITR/必要恢复及其它责任均不动。scope的目录模式保留，包括原cache，目标文件0600、原文父目录0700。

主代理顺序实施计划/工具与scope；独立正确性/维护PRE和本地合成控后主代理唯一新label inspect；独立重新hash/lstat/无跟随读取核验准备。以上均0删除/云/UI/模型/新原文，不执行旧collector；等待真实到期时另新label inspect，不重复准备label。

到期当轮先核主代理/进程/PR/工作树及全局 `.zerde-release-operation.lock` 独占，再公告三个精确路径、83保留/7目录和待核；公告链接scope完整保留清单。新notice的 announced_targets 必须等于scope原顺序，deadline_epoch原值、scope_sha256和announced_at真实UTCepoch；每个unlink意图距公告0至3600秒。公告不是再次请授权。未到期仅检查并同轮等待，每次不超过60秒；绝不apply探测。到期且全部hash/父目录/模式/身份/单硬链接/86库存保持，主代理持全局锁执行 `python3 -B expire_raw.py apply <新的唯一label>` 一次；本地操作锁禁止并行。逐文件核父目录描述符/目标身份再unlink，6个fsync的intent/result顺序留证，已成功unlink先记入内存，后close或journal失败仍报告已删事实。

独立代理待apply结束后，持同一全局锁第一次执行 `python3 -B verify_absence.py`。重新lstat三个路径不存在、83保留hash和7目录身份/库存不变；复算两ledger、scope、notice、intent、apply和6journal时间链。文件移除不是安全擦盘或所有云/外部副本消失，顺序核验不是文件系统事务。

hash/身份/库存变化、占用、notice过旧或未知均停止并保全partial；不得重apply或重建原文。新窄续接须独审，不能覆盖原失败。整批完成后计划/证据/task_manifest/TASKS/HANDOFF/RETAINED_COPIES及相关GitHub正文与automation同步。阶段状态如实区分准备/删除/独审/文档交付。

不改变原费用结论：38.65+6.18=44.83是账号发票摘要，非Zerde独占/付款/FreeTier；CE差0.0074992985保持UNKNOWN；Groq/DeepSeek无登录回复不重开页。运行PR257、配置PR251、S预算reader和五owner保持；不调用reader或部署。Z10/Z17/Epic仍OPEN，自然0/50有据0/20未知、production_ready=false。

任务板：主代理负责scope/两工具/计划，正确性与维护代理仅审核和合成控；PRE后主代理inspect，独立代理准备读回；到期主代理apply，独立代理verify；最后主代理文档/工单/automation，独立正确性/维护/最终读回。删除/发布/UI禁止并行；旧批次once全部冻结。

[主准备](evidence/2026-10-13-invoice-raw-expiry/preparation.safe.json)；[独立准备](evidence/2026-10-13-invoice-raw-expiry/independent.safe.json)。原主报告PENDING由后独审闭合，不改原字节。
