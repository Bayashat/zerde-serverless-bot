## 2026-10-09：共享 Gemini 配额 writer 已发布并完成实际包核验

PR257 构建源 `43561cfcf6ab3a8f8af95ee0cba396cac2dbae8c`、merge `10019418ca7bb1118213361c3847c5a80387b64c`。71项新回归、270项定向、2461项全测和三个CI job通过；两环境五入口ARM、实际五函数完整ZIP/共享层/配置保护主检独审以及各300秒稳定完成。实际仅Bot/MemoryWorker共同包更新，唯一非缓存源码为rate_limit.py；564个依赖pyc差异如实保留，其余三函数与层字节不变，PR251身份配置保持。

原writer、RATE key/PT日期、limit和48小时墙钟TTL不换。强读区分整行缺席与存在坏行；已有计数仅接受有限非负整数，写前拒绝坏值。合法行CAS设置精确next，至多三轮只重试明确RetryAttempts为真整数0的条件冲突；不明写不自动重写/退款。合法耗尽仍递增，原ClientError不可用结果与非ClientError/logger异常传播保持。没有观察到线上坏行或超额，不能把源码缺陷称为已发生线上事故，也不声称跨业务重送严格一次。

新实际包28例本地禁网ARM合成及独立直接原流/6模块/完整包/容器移除核验通过，存储和提供方为本地seam；没有新Telegram、模型、线上故障或自然样本测试。104文件费用闭包仅writer变化、原五Memory计费owner保持，新时点reader通过7次只读核验，非持续模型许可或实付。原final中的probe/budget pending是阶段记录，由后续真实回执闭合，不改冻结报告。

首次canonical本地KeyError发生在云上传前；静态控制流与保全输出将其定位到dev不含两个prod-only旧规则，原运行traceback未直接捕获，不能冒称直接异常栈证据；原dev15,263文件和原工具/失败回执保全。新V2只接受dev精确缺席、保留prod原约束，随后完成原dev首次ARM与prod首次构建/ARM；不冒称首次成功。执行前留证工具缺口和本地fixture失败均保留。发布包含真实云读取/资产准备和每环境单次Execute，不能将本地探针0云扩大为整轮0云；CI既有OIDC/CDK只读另计。

新增原文责任为Oct16 18:48:47.827167UTC，精确原文/含原文派生按本批release-raw-retention.safe.json；安全聚合/hash及完整ZIP保留。原十项期限不变，Oct13/14各两时点分开。Z01/Z10/Z12–Z17及Epic原状态保持，20工单14OPEN/6CLOSED，自然0/50有据、0/20未知、production_ready=false。Y相册旧绑定已失效，需新reader/工具绑定独审和新的Telegram独占窗口后另执行；本次不发送媒体。

[实际发布证据](evidence/2026-10-09-shared-quota-writer/release.safe.json)；[有限修复合同](SHARED_QUOTA_WRITER_REPAIR.md)；[精确保留台账](RETAINED_COPIES.md)。

## 原有限行为合同与发布前记录（历史阶段，已由上方实际回执闭合）

# 共享 Gemini quota writer 修复

当前阶段：本地实现与测试完成，独立代码审查进行中；尚未合并、发布或完成新实包验收。Z17/Epic 仍 OPEN，task_manifest 状态不变。

原 writer 将已有缺 request_count 的行初始化为 1，并在写入后用 int 转换计数。本轮没有观察到线上坏行或超额；这是源码及本地模拟复现。PR248 修复的是显式Gemini消费者门禁；另外两个Memory消费者已有拒绝无效返回的保护，本次沿同一个原writer修订，三个消费者调用协议均不变。

## 有限行为合同

- 原 stats 表、RATE scope/PT 日期 key、limit、PT 午夜加 48 小时 TTL 及三个消费者保持。仅 repositories/rate_limit.py 改变运行逻辑，不新增预算 owner、SDK 配置或坏行迁移。
- 每轮强读区分整行缺席与已有坏行。已有行仅接受非负真整数或有限整值 Decimal；缺属性、字符串、布尔、小数、负数等不写入、不改 TTL。
- 缺整行用 attribute_not_exists(stat_key)，合法行以旧 request_count 作 CAS，设置精确 next。合法耗尽仍沿原合同递增后返回 False，计数不是供应商请求数或实付。
- 最多三轮；仅 ConditionalCheckFailedException 且 ResponseMetadata.RetryAttempts 为真正整数 0 才重读竞争状态。缺失、畸形、非零重试元数据和其它错误不自动再次写入。
- 成功响应必须含精确 next；畸形响应保留可能已经写入的增量，不读回后再授予许可或退款。原 ClientError 不可用 sentinel (0, True) 保持，三个消费者拒绝；非 ClientError 和 logger 自身异常保持传播。
- 固定诊断只包含固定 reason code 与 scope，不输出坏行、异常正文、cause/context。无跨业务 attempt ID，因此不声称跨重送严格一次。

## 实际本地证据

私有入口：2026-10-09-shared-quota-writer。计划 PRE 与维护 PRE 均 ALIGNED。旧代码三个模拟坏行复现实际失败，原日志保留；修复后 270 项定向、2461 项全测通过。71 个新增测试覆盖存储形状、TTL、最后许可竞争、未知已写不重放以及显式/Memory 提取/Memory 回答三个真实编排。首次测试 fixture 77P/7F 和修订、首次格式化回执均保留，不称首次无问题。模拟 DynamoDB/网络故障不是线上坏行或真实模型测试。

## 发布验收仍待

当前线上字节仍 PR248 source 8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0，配置 PR251 source 59674f58cfa7e5f92170b88fa5e0bad5bdf81dff。新工具需冻结独审，两个环境五入口 ARM、Bot/Worker 实际包变化、其余三包/层和全部配置保护、主独读回及各 300 秒稳定后才算发布交付。随后新实包禁网探针、104 文件闭包仅 writer hash 改变与新预算 reader 绑定。旧 G reader 只适用旧包；Y 相册验收在新包发布后必须重新绑定，不沿旧许可发送。

原十项 UTC 保留职责和所有冻结 once 不变，见 RETAINED_COPIES。没有新 Telegram、模型或自然样本；production_ready=false。
