# 保留副本与到期责任（更新至2026-10-08）

当前剩余十一项独立UTC职责：Oct8日志、Oct11费用、Oct12Quiz、Oct13早次发票、Oct13晚次PR248失败元数据、Oct14早次公开文本、Oct14晚次配置发布、Oct15早次本批提及/Reply、Oct17 PITR、Nov1旧memory SYSTEM、Nov2旧stats SYSTEM；精确时分与逐文件身份见各段台账。

统一跟踪工单为Z10/#167；原各批次owner和回执不改写。Z20关闭仅代表已声明源码与在线资源退役，以下副本责任没有结束。[本批实际证据](evidence/2026-09-28-legacy-stats-final/final.safe.json)。

| 对象 | 当前状态与下一动作（UTC） | 责任依据 |
|---|---|---|
| 本批旧stats USER恢复备份 | 已精确删除并独审不存在；调用2026-10-05T08:18:54.216996Z（期限后18.264秒） | 实际创建时间＋7天，人工清理责任，AWS不会自动替我们删除；原owner R2/Z20，后续Z10跟踪 |
| 原旧记忆PITR职责 | 2026-10-17 16:20:38复查 | 保留原9月清零台账，不被后续删表期限替代 |
| S4旧memory SYSTEM备份 | AVAILABLE；AWS报告2026-11-01 11:46:02.425到期后只读复查 | 原TableId/精确备份身份，原S4回执 |
| 本批旧stats SYSTEM备份 | AVAILABLE；AWS报告2026-11-02 08:45:11.254到期后只读复查 | 本批实际创建与Expiry字段，精确原TableId绑定；不是推算或已删除 |
| 原统计分类AV临时文件 | 本批完成后提前移除并独审，原期限Oct4 10:35已履行 | 只移除原精确文件；文件移除不是安全抹盘 |
| 原3份本地密文归档及key | 2026-09-18 21:56:11.860005已移除，真实晚5h6m19.860s | 保留原失败/延迟事实，不重建、不重删 |
| 日志、DLQ、其他历史副本 | 仍按原清零台账逐项核对 | 删除队列/日志对象不证明所有历史导出和外部副本消失 |
| 用户原始Telegram导出 | 保留，不在删除范围 | 用户文件边界 |

本批USER清理已于2026-10-05履行，见[独立证据](evidence/2026-10-05-user-backup-expiry/independent.safe.json)；不得重新删除或恢复该备份。SYSTEM到期只读复查，服务未清除则记录真实状态继续跟踪。不能重新restore到原表或现役表，不能启用旧writer。所有当前操作者、恢复验证和本地分类文件清理工具都已结束，禁止重跑；未来到期步骤另建精确工具与回执。

现役表自己的PITR和业务恢复数据继续保留，不属于这张旧资源副本清单。线上不存在与物理副本消退分别验收；只要上述责任或整体验收仍未完成，现有zerde自动任务继续保留。

## Z02本次CloudWatch临时原文（独立责任）

10月7日已准备新的九文件精确清理工具和独立核验；当前仅准备/到期前核验，尚未删除。范围、保留41文件及失败停止规则见[CLOUDWATCH_RAW_EXPIRY](CLOUDWATCH_RAW_EXPIRY.md)。不增减原八项责任或变更期限。

2026-10-01 17:13:39.091570 UTC开始的单次只读采集产生9份必要原始回执（8份API响应和1份所选身份），均0600。按原契约7天后，即2026-10-08 17:13:39.091570 UTC，删除精确manifest列明的这些文件及任何登记的含原文派生文件，再独立核不存在。私有精确清单为验收根`2026-10-01-z02-cloudwatch-capture/raw-retention.safe.json`；只删该清单，不扫整个目录。安全hash/聚合报告保留；不改Z10原四期限，也不以本地文件移除声称安全擦盘或CloudWatch历史物理副本全部消失。

## Z17九月费用原文（独立责任）

2026-10-04 17:01:48.147210UTC开始的单次费用采集，实际6份AWS回执；另有2份Google UI下载CSV及1份主操作者UI观察。私有清单为验收根`2026-10-04-september-costs/raw-retention.safe.json`和`provider-raw-retention.safe.json`；实际文件列表/hash另见聚合。九个精确文件及登记的原文派生共同于2026-10-11 17:01:48.147210UTC人工删除并独审；CSV/观察采用更早的同一期限，没有延长到下载后七天。权限0600、原文目录0700，下载CSV已精确移出Downloads。安全聚合/hash保留；其余责任保持；Oct5旧stats USER已按上方回执履行，Oct8日志原文仍待清理。工具、原始采集和独立复算均冻结，不重跑旧动态月份脚本。

## Z16答案重送验收原文（独立责任）

2026-10-05 17:15:22.532382UTC开始的受控验收，所有实际API响应、请求参数、目标快照、UI观察及登记含原文派生采用同一七日期限：2026-10-12 17:15:22.532382UTC。精确私有清单为验收根`2026-10-05-quiz-answer-redelivery/raw-retention.safe.json`；目录0700、文件0600，逐文件登记/hash，完成后人工精确清理并独立核不存在。工具上限不是实际文件数量，安全聚合/hash保留；新准备窗口和独立读取不能延长原期限。此责任独立于Oct8、Oct11、Oct17、Nov1、Nov2，不重新删除已完成USER备份或旧AV。

## Z17账号发票摘要原文（独立责任）

2026-10-06 08:06:04.659429UTC首次采集开始。原端点校验误停仅产生1份STS回执；V2产生1份STS和1份发票摘要，共3个实际原文文件。私有验收根`2026-10-06-provider-cost-gaps/invoice-retention.safe.json`与`invoice-v2/invoice-retention.safe.json`逐一绑定相对路径/hash；实际路径为`invoice-raw/001.private.json`、`invoice-v2/invoice-raw/001.private.json`、`invoice-v2/invoice-raw/002.private.json`。原文0600、目录0700，V2采用原更早期限，统一于2026-10-13 08:06:04.659429UTC人工精确删除并独审不存在，全部登记原文派生同一期限（当前无额外派生）。安全聚合/hash保留；API上限不当实际文件数量，不通配删除、不延长既有Oct8/11/12/17/Nov1/2责任。两供应商登录页没有产生账户原文或额外账单保留义务。

以下为本轮新增前的七项职责摘要（均继续保持）：Oct8日志原文、Oct11费用原文、Oct12Quiz原文、Oct13本次发票原文、Oct17原PITR、Nov1旧memory SYSTEM、Nov2旧stats SYSTEM；精确时分与身份按各段/manifest。早次到期前先预检并同轮等待（单次不超过60秒），不故意拖到下轮；真实延误如实记。所有已结束采集/清理/恢复once保持冻结，文件移除不等于安全抹盘。

## PR248首次dev读回失败元数据（第八项独立责任）

最早采集2026-10-06 18:26:43.519150UTC，三份原文的人工清理期限保持2026-10-13 18:26:43.519150UTC。dev第一次实际包主读在第三ZIP下载时超时，原七文件完整保全于验收根`2026-10-06-explicit-quota-guard/post-main-dev-download-incomplete`。根失败部分只含`responses.private.json`、`artifact-responses.private.json`、`snapshot.private.json`三份元数据及登记含原文派生；三文件0600，目录0700，没有新增原文派生。

权威迁移后精确清单是`2026-10-06-explicit-quota-guard/failed-dev-download-retention.safe.json`，逐项绑定原hash/身份/期限；目录内原unreviewed-retention清单保留历史字节，其旧路径已经由成功轮使用，绝不能据旧路径误删成功回执。按新清单另做工具PRE、到期精确删除并独审；两份完整代码ZIP与安全hash/聚合报告继续作为发布审计保留，不在根三份原文内。既有七项职责和已履行USER/AV记录不变，文件移除不是安全擦盘。另有独立首STS ReadTimeout失败，零响应零包下载；原review/空metadata/原ledger三文件完整归档post-independent-dev-sts-timeout，空metadata-responses.private.json由failed-independent-dev-retention.safe.json精确绑定并采用本批更早的同一期限，不延长原18:51:50.905062期限。该空记录不是AWS响应；第八项合计根三元数据加独立空记录四文件。新只读续接成功不改写两次首次INCOMPLETE。

## Z01公开文本原文（第九项独立责任）

2026-10-07 20:45:55.665021UTC开始，本批原始API、UI观察和所有含原文派生统一于2026-10-14 20:45:55.665021UTC人工精确删除并独审。私有清单`2026-10-08-z01-public-text/raw-retention.safe.json`当前128项：97根API、20独立API、10主UI、1审核源派生，最终ledger SHA`d0f60d4c7d29d2315cd1fb88a4e7698231d164be604d9cc98dbe2dbe71b3e61c`。全部已登记/hash/0600，目录0700；审核源最初迟登记与临时0644偏差已整改，但原报告保留，期限未延长。未来按当时实际ledger逐个核身份/hash，新工具PRE后清理，不通配；安全聚合保留，不以文件移除声称安全擦盘。原八项精确UTC期限、用户导出和现役PITR保持。

## PR251配置发布原文（第十项独立责任）

首次采集2026-10-07 21:48:46.021161UTC，原始API、完整配置快照、模板及登记含原文派生共1030个精确文件，统一于2026-10-14 21:48:46.021161UTC人工删除并独审。权威清单为验收根 `2026-10-08-dev-bot-identity-fix/release-raw-retention.safe.json`，最终SHA `a23b0b8eff40e11356aaad08902642ff8570be816168090a9975cc03a04cd6ea`；0600/0700，全部CAPTURED。原首次执行轮询失败及只读续接沿同一期限，不延长或重建原文。按届时实际ledger逐个核身份/hash，新工具PRE后精确删除；安全聚合、代码ZIP及现有assets桶中唯一配置审计模板保留。模板不是新代码包，不属于该本地原文清理范围。第九项N原文比本项早约一小时，不合并两期限，原八项保持。文件移除不等于安全擦盘或云副本全无。

## Z01修复后提及与Reply原文（第十一项独立责任）

本批首次采集2026-10-08 08:17:52.186798UTC，85份实际API/UI原文及登记含原文派生统一于2026-10-15 08:17:52.186798UTC人工精确删除并独审。私有清单为验收根`2026-10-08-z01-mention-reply/raw-retention.safe.json`，最终ledger SHA`d97fbbfd13d90169dacfcdc7cbe486c7277a6cda949f16c4c672913a84b3f0ed`，所有文件0600、目录0700、CAPTURED；独立17读沿原期限，不延期。工具上限不当实际数量，原生数字ID/链接缺失不由后续补猜。届时按实际ledger逐文件hash/身份、新工具PRE与精确公告后删除，安全聚合/hash保留，文件移除不是安全擦盘；其余十项精确UTC期限、用户导出与现役PITR保持。
