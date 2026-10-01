# Quiz命令日志内容旁路：发现与修复

2026-10-01晚，对PR235实际dev Bot做单次8个只读API采集。374秒窗口完整分页取得38条记录，选中一个真实Lambda请求，START/END/REPORT完整、27条应用JSON、入口/凭据验证/授权metadata各1；Filter与Get逐事件多重集合一致。实际LOG_LEVEL为DEBUG，没有修改等级。具体Telegram messageID关联未证，不能用于补2404/queued反馈链接。

固定评分发现一个未隐藏的自由topic字段，保留FAIL；另外19条不在预设producer白名单内，保留原INCOMPLETE条目，不采集后改白名单凑PASS。结果没有匹配到既定凭据形状，不据此宣称所有历史日志无泄漏。独立原文复核确认同一条topic内容事件被两API各读到一次；实际值只证明为技术标签，未证明个人敏感信息或凭据泄漏。19条原工具未分类记录独立映射为统计初始化1条、静态handler注册4条、静态命令注册12条和费用metadata2条，原FAIL/INCOMPLETE不改；不把静态风险都说成实际线上泄漏。

## 原因与本地修复

`handle_quiz_generate`把自由输入topic直接放进诊断extra，共享formatter未把topic列为内容键；普通正文因此能通过凭据正则。现在仅记录topic_chars，完整topic仍按原payload传给Quiz。沿同调用链，`LambdaInvoker.invoke_async`失败诊断改为固定消息/function_name/error_type，不输出任意异常正文或chain，仍单次Event调用、成功True/失败False。同步invoke没有改，不宣称由本次测试覆盖。

没有改变授权、parser、Quiz持久请求/outbox、计分、RPD、Memory五费用owner、共享formatter或层。新测试使用真实Context/parser/handler、LambdaInvoker与JSONFormatter/Adapter，只stub外部IO：多语非凭据topic完整交付但不进日志；cause/context正文不进入最终流；单次True/False协议保持。修复前5fail/1pass，修复后6新例与logger集合30pass，完整2340pass/1warning。代码正确性与维护独审通过。

## 发布与验收边界

本提交仍是本地修复，当前运行PR235。下一步CI、实际ARM五入口、精确代码变更集、两环境实际五函数ZIP/层/配置保护与独审，预算reader重新绑定；只有包含这两个模块的Bot/MemoryWorker资产更新，其它实际包/层保持。新实际包重验两个出口后，再按原Z02有限契约决定收口。旧线上FAIL永久保留，不被修复后的结果覆盖。

本轮没有新发消息、模型请求、Lambda Invoke、队列Receive/Purge、控制/计量或支付修改。原raw/once冻结，9份私有回执在2026-10-08 17:13:39.091570UTC到期；原四副本期限、Quiz精确UI缺口、其它业务/账单和自然0/50、0/20、production_ready=false保持。

[独立安全聚合](evidence/2026-10-01-z02-cloudwatch-capture/final-reviewed.safe.json)；[独立原文复核](evidence/2026-10-01-z02-cloudwatch-capture/independent-final.safe.json)。
