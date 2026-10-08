# 九月费用九份原文：Oct11到期清理准备

已完成新工具PRE、只读inspect与独立本地复核，尚未删除。原期限固定2026-10-11 17:01:48.147210UTC；唯一源为验收根`2026-10-04-september-costs`，新执行目录`2026-10-11-september-cost-raw-expiry`。

准备删除的精确九路径：

- raw/001.private.json
- raw/002.private.json
- raw/003.private.json
- raw/004.private.json
- raw/005.private.json
- raw/006.private.json
- provider-raw/google-dev-september-usage.csv
- provider-raw/google-prod-september-project.csv
- provider-raw/provider-ui-observation.private.json

raw/007至043为37个未创建预留槽，不是删除目标。scope列明57份其余保留文件、6个目录；原两ledger、历史hash/安全费用报告、旧失败和GitHub审计保留，其余九项原文/副本责任和用户导出/现役PITR不变。本地新工具不调用AWS、不复制原文、不重查账单。

到期当轮先精确公告九目标/保留/待核，保存实际公告时点和scope SHA，每次unlink意图距公告≤1小时。全部字节/身份、父目录无symlink、raw文件0600、源根及两原文目录0700与时点通过才执行唯一apply；其余目录按scope原模式保留。每个unlink成功立即记入结果，后续日志/close失败也保留真实已删项。任何未知停下，另立精确剩余续接，不重复apply。成功后独立核九路径不存在、57hash保持、6目录身份与公告/intent/journal/时间一致。到期早到同轮预检等待（每次≤60秒），不故意拖晚；迟延如实记。文件移除不是安全擦盘。

[准备回执](evidence/2026-10-11-september-cost-raw-expiry/preparation.safe.json)；[独立准备复核](evidence/2026-10-11-september-cost-raw-expiry/independent.safe.json)。Z10/Epic继续OPEN，不把prepare记成履行。
