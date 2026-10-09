# 共享 Gemini quota writer 修复

当前阶段：本地实现与测试完成，独立代码审查进行中；尚未合并、发布或完成新实包验收。Z17/Epic 仍 OPEN，task_manifest 状态不变。

原 writer 将已有缺 request_count 的行初始化为 1，并在写入后用 int 转换计数。本轮没有观察到线上坏行或超额；这是源码及本地模拟复现。PR248 已修三个消费者的无效返回门禁，本次只修同一个原 writer。

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
