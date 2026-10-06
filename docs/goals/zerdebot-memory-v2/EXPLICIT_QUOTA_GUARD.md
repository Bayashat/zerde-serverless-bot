# 显式 Gemini 准入校验

## 问题与唯一修改点

当前PR242的`RateLimitRepository.increment_and_check`对DynamoDB ClientError返回`(0, True)`。显式`GeminiClient.group_chat_reply`原先仅检查`within_limit`，因而可能在计数未确认时继续HTTP。Memory V2抽取/选择已有严格正数检查和原预算预留，本切片不改其owner。

仅在`GeminiClient`消费原返回值的边界增加验证：`type(count) is int`且count>=1，`type(within_limit) is bool`。无法解包或类型/值无效时抛`GeminiQuotaUnavailableError(RuntimeError)`，与Unavailable、RPDExhausted及原provider重试异常分离；不记录原返回对象。writer调用本身的异常保持原样。合法true继续原路径，合法false保持原额度耗尽/备用策略。

## 调用与恢复语义

计数不明后本次链不再发新的模型HTTP、不切备用供应商；先前真实尝试或独立Memory选择可能已经发生，不能声称整条原请求零调用。原显式交付异常和SQS失败重试协议继续处理失败，不新建预算、通知或恢复owner。完整prompt/上下文、原权限、发送租约和最终发送栅栏保持。

共享writer的坏存量字段转换、缺字段补齐以及备用供应商完整使用费证据不在这一个消费边界修复中，明确留在Z17；不清理历史UNKNOWN、改变原计量epoch/DAY或回填历史次数。

## 有限验收

18个新测试通过实际ExplicitDelivery/MemoryRepo/GroupAgent/Gemini编排，替换外部HTTP：真实repository ClientError sentinel、13类畸形返回、首次503后第二次准入不明、owner异常保持，以及合法准入/额度耗尽两个正控。断言HTTP次数、备用provider和最终发送。原测试不删除；完整测试及pre-commit、独立代码/维护审查和CI仍须通过。

发布仅允许Bot/MemoryWorker共同包的gemini_client非缓存源码变化；如实核pyc差异，News/Quiz/Operations和共享层完整字节保持。新受审操作器绑定PR242实际发布、当前候选commit；五入口ARM、两环境实际五函数ZIP/层/配置/控制保护主独读回及300秒稳定后才称已上线。新实际包再作本地禁网合成探针和独立原流复核；最后重绑104文件预算reader，原五计费owner逐字不变。只读时点PASS不是持久许可。

当前本地实现/验证进度见FINISH_EXECUTION；本契约不是部署或真实Telegram验收结果。Z01/Z17/Epic保持OPEN；自然质量与七项副本责任继续。不重跑任何已结束公开题/故障注入/回放或冻结报告。
