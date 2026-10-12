# 保留副本与到期责任（更新至2026-10-12）

当前剩余九项独立UTC职责：Oct13早次发票、Oct13晚次PR248失败元数据、Oct14早次公开文本、Oct14晚次配置发布、Oct15早次本批提及/Reply、Oct16本次共享writer发布原文、Oct17 PITR、Nov1旧memory SYSTEM、Nov2旧stats SYSTEM；精确时分与逐文件身份见各段台账。

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

## Z02本次CloudWatch临时原文（已履行）

九份精确原文已于原期限2026-10-08 17:13:39.091570UTC之后逐项移除；首个完成2026-10-08T17:13:39.209172+00:00，最后2026-10-08T17:13:39.211508+00:00，实际晚0.117602至0.119938秒。独立重新核九路径不存在及41个列明同目录保留文件hash不变，原ledger SHA27b80ee4a7c224c97353c6dadb96458207932d332140a496bd41e2f678e729ea保留。见[实际结果](evidence/2026-10-08-cloudwatch-expiry/final.safe.json)和[独立回执](evidence/2026-10-08-cloudwatch-expiry/independent.safe.json)。唯一apply与verify已结束，不重删、不重采集/恢复原文。原普通topic FAIL和19未分类条目保留；文件移除不是安全擦盘或云历史副本全无。其他十项期限、用户导出/现役PITR不变。

以下为准备期原记录，不作当前待删指令：

10月7日已准备新的九文件精确清理工具和独立核验；当前仅准备/到期前核验，尚未删除。范围、保留41文件及失败停止规则见[CLOUDWATCH_RAW_EXPIRY](CLOUDWATCH_RAW_EXPIRY.md)。不增减原八项责任或变更期限。

2026-10-01 17:13:39.091570 UTC开始的单次只读采集产生9份必要原始回执（8份API响应和1份所选身份），均0600。按原契约7天后，即2026-10-08 17:13:39.091570 UTC，删除精确manifest列明的这些文件及任何登记的含原文派生文件，再独立核不存在。私有精确清单为验收根`2026-10-01-z02-cloudwatch-capture/raw-retention.safe.json`；只删该清单，不扫整个目录。安全hash/聚合报告保留；不改Z10原四期限，也不以本地文件移除声称安全擦盘或CloudWatch历史物理副本全部消失。

## Z17九月费用原文（已履行）

原期限2026-10-11 17:01:48.147210UTC不变。九个精确文件实际首次/末次unlink为2026-10-11T21:20:31.636119+00:00和2026-10-11T21:20:31.639021+00:00，分别晚15523.488909秒和15523.491811秒（约4小时18分43秒）。本轮首次实际时钟检查已经晚于期限，后续执行间隔原因UNKNOWN，不猜测设备或调度原因，不改写为按时完成。

唯一apply与独立不存在核验均完成：6份AWS原始响应、2份Google CSV和1份UI观察已移除；57份列明保留文件hash、6目录身份和37个未创建槽保持，18条逐项intent/result与公告、原ledger和实际时点一致。raw/007–043从未创建，不算已删；安全费用聚合、旧失败、原账本和全部费用UNKNOWN保留，原37在线对象计数不增。文件移除不是安全擦盘或所有云/外部副本消失。

以下为Oct11履行时的历史摘要，待办已由本文件顶部当前九项覆盖，不作当前执行指令：

本清理/核验0云API、UI、模型或新运行部署，后续CI既有OIDC/CDK只读预览另计。运行仍PR257字节、PR251配置，唯一时点reader仍共享writer批次S；本轮不重复任何旧reader/采集/发布。剩余十项职责中最近是Oct12 17:15:22.532382UTC答案原文247文件，其准备已完成，apply尚未执行；Oct13/14各双时点及Oct15/16/17/Nov1/Nov2保持。用户导出、现役PITR和必要恢复数据保留。

Z10/Z17/Epic继续OPEN，20任务14OPEN/6CLOSED保持，自然0/50有据、0/20未知，production_ready=false。相册尚未重绑定新包，也未获得新的Telegram独占窗口；本轮没有现场或业务验收。

[精确清理契约](SEPTEMBER_COST_RAW_EXPIRY.md)；[实际结果](evidence/2026-10-11-september-cost-raw-expiry/final.safe.json)；[独立不存在核验](evidence/2026-10-11-september-cost-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

以下为已冻结准备期记录，不作待删指令：

2026-10-09新精确清理准备已完成：九实际文件、57保留文件、6目录由新工具inspect及独立本地复核通过，零删除/云调用。原期限不变；[执行契约](SEPTEMBER_COST_RAW_EXPIRY.md)列精确目标，不能用43槽代替实际文件或重跑旧collector。到期公告/唯一apply/独立不存在尚待。

2026-10-04 17:01:48.147210UTC开始的单次费用采集，实际6份AWS回执；另有2份Google UI下载CSV及1份主操作者UI观察。私有清单为验收根`2026-10-04-september-costs/raw-retention.safe.json`和`provider-raw-retention.safe.json`；实际文件列表/hash另见聚合。九个精确文件及登记的原文派生共同于2026-10-11 17:01:48.147210UTC人工删除并独审；CSV/观察采用更早的同一期限，没有延长到下载后七天。权限0600、原文目录0700，下载CSV已精确移出Downloads。安全聚合/hash保留；其余责任保持；Oct5旧stats USER已按上方回执履行，Oct8日志原文已按上方精确回执履行。工具、原始采集和独立复算均冻结，不重跑旧动态月份脚本。

## Z16答案重送验收原文（已履行）

原期限2026-10-12 17:15:22.532382UTC不变。247个精确文件（246份private JSON及含原文click-intent.safe.json）已逐项移除；首次/末次unlink为2026-10-12T17:15:22.647203+00:00、2026-10-12T17:15:22.983452+00:00，实际晚0.114821至0.451070秒，原因UNKNOWN，不改写为提前或绝对准时。独立重新lstat全部目标不存在、217保留hash/18目录身份及剩余库存保持，494条intent/result与公告、原ledger和时间链一致。原__pycache__0755保留。

原PARTIAL_UNCONFIRMED_UI、旧STOP/失败/安全聚合和原ledger保持；清理不证明投票提交、HTTP500重送或一次计分通过，不重发/重答旧题。文件移除不是安全擦盘或所有云/外部副本消失，顺序核验不是文件系统事务。清理和本地核验0云/UI/模型、新原文或运行部署；后续CI既有OIDC/CDK只读另计。

剩余九项责任：Oct13早次发票3、晚次旧PR248失败4；Oct14早次公开文本128、晚次配置1030；Oct15提及Reply85；Oct16共享writer1426；Oct17 PITR；Nov1旧memory SYSTEM；Nov2旧stats SYSTEM。各原精确期限见副本台账，不合并双时点。Oct11费用/Oct8日志/USER/AV/三归档key已履行且真实延误保留，不重删重建；用户导出、现役PITR和必要恢复保留。

运行PR257/配置PR251/S reader保持。Z10/Z16/Epic继续OPEN，20任务14OPEN/6CLOSED、自然0/50有据0/20未知及production_ready=false不变；相册仍待新包重绑和新的Telegram独占窗口，未操作UI。

[清理契约](QUIZ_ANSWER_RAW_EXPIRY.md)；[实际聚合](evidence/2026-10-12-quiz-answer-raw-expiry/completion.safe.json)；[独立不存在](evidence/2026-10-12-quiz-answer-raw-expiry/completion-independent.safe.json)；[副本台账](RETAINED_COPIES.md)。

## 以下为此前冻结阶段，不作当前待删或重跑指令

2026-10-09已完成新工具和只读准备：247实际目标、217保留文件与18目录主独核验通过，尚未删除，原期限不变。click-intent.safe.json仍属原文。到期按[新精确契约](QUIZ_ANSWER_RAW_EXPIRY.md)及私有scope执行一次；原业务PARTIAL与全部已结束once保持。

2026-10-05 17:15:22.532382UTC开始的受控验收，所有实际API响应、请求参数、目标快照、UI观察及登记含原文派生采用同一七日期限：2026-10-12 17:15:22.532382UTC。精确私有清单为验收根`2026-10-05-quiz-answer-redelivery/raw-retention.safe.json`；目录0700、文件0600，逐文件登记/hash，完成后人工精确清理并独立核不存在。工具上限不是实际文件数量，安全聚合/hash保留；新准备窗口和独立读取不能延长原期限。此责任独立于Oct8、Oct11、Oct17、Nov1、Nov2，不重新删除已完成USER备份或旧AV。

## Z17账号发票摘要原文（独立责任）

新三文件准备已独审通过：83保留/7目录/86库存，原期限不变，尚未apply。见[新契约](INVOICE_RAW_EXPIRY.md)。

2026-10-06 08:06:04.659429UTC首次采集开始。原端点校验误停仅产生1份STS回执；V2产生1份STS和1份发票摘要，共3个实际原文文件。私有验收根`2026-10-06-provider-cost-gaps/invoice-retention.safe.json`与`invoice-v2/invoice-retention.safe.json`逐一绑定相对路径/hash；实际路径为`invoice-raw/001.private.json`、`invoice-v2/invoice-raw/001.private.json`、`invoice-v2/invoice-raw/002.private.json`。原文0600、目录0700，V2采用原更早期限，统一于2026-10-13 08:06:04.659429UTC人工精确删除并独审不存在，全部登记原文派生同一期限（当前无额外派生）。安全聚合/hash保留；API上限不当实际文件数量，不通配删除、不延长既有Oct8/11/12/17/Nov1/2责任。两供应商登录页没有产生账户原文或额外账单保留义务。

以下为本轮新增前的七项职责摘要（均继续保持）：Oct8日志原文、Oct11费用原文、Oct12Quiz原文、Oct13本次发票原文、Oct17原PITR、Nov1旧memory SYSTEM、Nov2旧stats SYSTEM；精确时分与身份按各段/manifest。早次到期前先预检并同轮等待（单次不超过60秒），不故意拖到下轮；真实延误如实记。所有已结束采集/清理/恢复once保持冻结，文件移除不等于安全抹盘。

## PR248首次dev读回失败元数据（第八项独立责任）

新四迁移目标准备已独审通过：12保护/5目录/两archive10库存，成功四同名路径及两ZIP保留；原期限不变，尚未apply。见[新契约](FAILED_READBACK_RAW_EXPIRY.md)。

最早采集2026-10-06 18:26:43.519150UTC，三份原文的人工清理期限保持2026-10-13 18:26:43.519150UTC。dev第一次实际包主读在第三ZIP下载时超时，原七文件完整保全于验收根`2026-10-06-explicit-quota-guard/post-main-dev-download-incomplete`。根失败部分只含`responses.private.json`、`artifact-responses.private.json`、`snapshot.private.json`三份元数据及登记含原文派生；三文件0600，目录0700，没有新增原文派生。

权威迁移后精确清单是`2026-10-06-explicit-quota-guard/failed-dev-download-retention.safe.json`，逐项绑定原hash/身份/期限；目录内原unreviewed-retention清单保留历史字节，其旧路径已经由成功轮使用，绝不能据旧路径误删成功回执。按新清单另做工具PRE、到期精确删除并独审；两份完整代码ZIP与安全hash/聚合报告继续作为发布审计保留，不在根三份原文内。既有七项职责和已履行USER/AV记录不变，文件移除不是安全擦盘。另有独立首STS ReadTimeout失败，零响应零包下载；原review/空metadata/原ledger三文件完整归档post-independent-dev-sts-timeout，空metadata-responses.private.json由failed-independent-dev-retention.safe.json精确绑定并采用本批更早的同一期限，不延长原18:51:50.905062期限。该空记录不是AWS响应；第八项合计根三元数据加独立空记录四文件。新只读续接成功不改写两次首次INCOMPLETE。

## Z01公开文本原文（第九项独立责任）

2026-10-07 20:45:55.665021UTC开始，本批原始API、UI观察和所有含原文派生统一于2026-10-14 20:45:55.665021UTC人工精确删除并独审。私有清单`2026-10-08-z01-public-text/raw-retention.safe.json`当前128项：97根API、20独立API、10主UI、1审核源派生，最终ledger SHA`d0f60d4c7d29d2315cd1fb88a4e7698231d164be604d9cc98dbe2dbe71b3e61c`。全部已登记/hash/0600，目录0700；审核源最初迟登记与临时0644偏差已整改，但原报告保留，期限未延长。未来按当时实际ledger逐个核身份/hash，新工具PRE后清理，不通配；安全聚合保留，不以文件移除声称安全擦盘。原八项精确UTC期限、用户导出和现役PITR保持。

## PR251配置发布原文（第十项独立责任）

首次采集2026-10-07 21:48:46.021161UTC，原始API、完整配置快照、模板及登记含原文派生共1030个精确文件，统一于2026-10-14 21:48:46.021161UTC人工删除并独审。权威清单为验收根 `2026-10-08-dev-bot-identity-fix/release-raw-retention.safe.json`，最终SHA `a23b0b8eff40e11356aaad08902642ff8570be816168090a9975cc03a04cd6ea`；0600/0700，全部CAPTURED。原首次执行轮询失败及只读续接沿同一期限，不延长或重建原文。按届时实际ledger逐个核身份/hash，新工具PRE后精确删除；安全聚合、代码ZIP及现有assets桶中唯一配置审计模板保留。模板不是新代码包，不属于该本地原文清理范围。第九项N原文比本项早约一小时，不合并两期限，原八项保持。文件移除不等于安全擦盘或云副本全无。

## Z01修复后提及与Reply原文（第十一项独立责任）

本批首次采集2026-10-08 08:17:52.186798UTC，85份实际API/UI原文及登记含原文派生统一于2026-10-15 08:17:52.186798UTC人工精确删除并独审。私有清单为验收根`2026-10-08-z01-mention-reply/raw-retention.safe.json`，最终ledger SHA`d97fbbfd13d90169dacfcdc7cbe486c7277a6cda949f16c4c672913a84b3f0ed`，所有文件0600、目录0700、CAPTURED；独立17读沿原期限，不延期。工具上限不当实际数量，原生数字ID/链接缺失不由后续补猜。届时按实际ledger逐文件hash/身份、新工具PRE与精确公告后删除，安全聚合/hash保留，文件移除不是安全擦盘；其余十项精确UTC期限、用户导出与现役PITR保持。

## PR257共享writer发布原文（新增独立责任）

首次采集2026-10-09 18:48:47.827167UTC；全部实际API/config/template及登记含原文派生统一于2026-10-16 18:48:47.827167UTC人工精确删除并独审。私有ledger为`2026-10-09-shared-quota-writer/release-raw-retention.safe.json`，实际hash见[交付证据](evidence/2026-10-09-shared-quota-writer/release.safe.json)，只按最终CAPTURED项逐个核身份/hash；NOT_CREATED/预留槽不当实际文件。0600/0700，原期限不因失败/续接延期；完整ZIP、纯源码和安全聚合保留。到期当轮新PRE、精确公告删/保留/待核且每项unlink距公告不超过一小时，未到期不apply；早到同轮等至期限，每次不超过60秒。实际失败保留partial另窄续接，不重建原文。文件移除不是安全擦盘；原十项期限、用户导出及现役PITR不变。
