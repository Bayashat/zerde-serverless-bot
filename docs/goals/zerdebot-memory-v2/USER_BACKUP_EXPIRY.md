# 唯一旧stats USER备份到期交付

旧stats的唯一USER恢复备份 `zerde-retirement-stats-20260928` 已删除，主检和独立查询均确认精确备份不存在。删除请求实际始于2026-10-05T08:18:54.216996Z，比原期限晚18.264秒；没有提前删除或延长期限。一次DeleteBackup获HTTP200且原身份一致，独立17次只读确认旧表仍不存在、六张现役表身份/PITR配置投影及两份SYSTEM完整元数据保持。

## 范围与实际证据

- 原七日合同：2026-09-28 08:18:35.953UTC创建，到期2026-10-05 08:18:35.953UTC。期限和原owner保持；Z10统一跟踪。
- 主预检17次只读；执行阶段34次API（其中仅1次删除）；独立17次只读。两次精确身份门禁、本机与新AWS响应时间均在期限之后才允许删除。
- 前后六表比对限TableId/ARN/名称/键/ACTIVE/删除保护及PITR配置，排除会移动的恢复窗口时间；没有扫描业务行。两份SYSTEM完整BackupDescription不变，各自期限保留。
- 最终精确DescribeBackup返回BackupNotFound；旧表DescribeTable返回ResourceNotFound。独立核验重新读AWS，非主聚合结果复述，也非跨资源事务。
- 两次本地hash编码断言误停为0云操作，确认原算法为canonical JSON字符串后绑定成功；不是线上备份异常。独立工具v1未云执行，v2只补ACK原始响应身份和intent/实际调用时间区分，首版证据保留。

## 仍待与保护边界

Z10继续OPEN：CloudWatch九份原文于10月8日17:13:39.091570UTC、九月费用九份原文于10月11日17:01:48.147210UTC精确清理；原PITR于10月17日16:20:38UTC复查；旧memory SYSTEM于11月1日11:46:02.425UTC、旧stats SYSTEM于11月2日08:45:11.254UTC服务到期后精确只读核验。日志/DLQ及其他原台账责任保持；用户导出、现役PITR和业务恢复数据保留。

没有读取备份行内容、恢复旧表、删除其它资源或修改bot。线上/备份API不可用不等于AWS介质安全擦除或所有副本物理清空。原37个在线退役对象计数不因删除一个恢复副本变成新的在线资源批次。

[主结果](evidence/2026-10-05-user-backup-expiry/root.safe.json) · [独立结果](evidence/2026-10-05-user-backup-expiry/independent.safe.json) · [聚合](evidence/2026-10-05-user-backup-expiry/final.safe.json)

AWS契约：[DeleteBackup](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_DeleteBackup.html)、[DescribeBackup](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_DescribeBackup.html)。按精确BackupArn删除和查询；只把对应明确不存在错误用作缺席证据。
