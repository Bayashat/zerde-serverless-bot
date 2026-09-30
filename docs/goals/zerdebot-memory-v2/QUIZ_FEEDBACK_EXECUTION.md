# Quiz 已保留请求的反馈修复

状态：已实现、正确性与维护独审通过，最终全测/CI/实际发布仍待。本文件不是上线证明。

## 问题与目标

9月30日真实受控准入失败已保留原请求和恢复outbox，但旧统一失败提示要求用户重发；同一请求随后自动发题成功。反馈应说明实际已持久化状态，避免用户重复发题。提示发送本身失败不能让整个生成调用重试。

## 单一所有者与接口

原publication execution/outbox事务继续拥有状态与恢复；原status、reason、retryable和业务异常保持。服务仅增加feedback_code，展示入口按固定语言键映射，不解析reason猜测状态、不暴露原始错误。

- queued：仅在原失败状态成功持久化后，告知请求已保存、后台尝试、无需重发；不承诺完成时间或成功。
- processing：已有处理占用；不能声称本次已保存。
- needs_review：UNKNOWN或已持久CONFLICT，交管理员核对，不自动重发。
- expired/rejected：原终止或请求标识无效，说明当前请求不能继续。
- unconfirmed：未知展示码保守提示，不能宣称已排队。
- DONE成功静默，不额外发送提示。claim、prepare、mark、finalize及提交不明异常仍穿透；不能谎报已保存。

生成函数位于展示catch之外。仅提示发送及诊断记录是尽力而为，false/None/异常均不改变业务结果、不新增发送/模型重试。实际QuizSender的send_message日志仅保留错误类型；sendPoll语义不变。该第三源文件是一项独审发现的必要窄修复：模拟sender不能证明真实发送器不会记录异常正文。

## 范围与切换

三个源文件：quiz_service.py、translations.py、quiz_sender.py；事务与准入owner不变。两测试文件覆盖状态、四语反馈、实际sender+最终formatter安全及恢复幂等。没有新状态表、钱包、队列、反馈outbox或旁路。原统一genquiz_failed展示路径删除，Bot其他翻译不受影响。

发布仅更新dev/prod Quiz代码，仍对两环境全部五函数、层、配置和保护项做实际读回；Bot/Worker/News/Operations/层沿用核验的实际字节。新发布后重绑原104文件Memory预算reader，不改五费用owner、真实计量或UNKNOWN。无新群/生产记忆、模型调用测试或付款操作。

## 验证和停止条件

本地使用原事务夹具检查持久化后排队反馈、Busy/EXPIRED/UNKNOWN/CONFLICT、缺请求ID、提交前后错误穿透、提示和诊断失败、同generation原恢复及DONE不重复。真实Telegram旧轮次冻结，不重发旧命令或复答旧题。

状态/恢复语义漂移、未确认持久化却宣称已保存、提示导致重新生成、原文进入日志、控制/预算owner改变均停止修正。独审、CI、ARM及真实部署读回是各自独立证据；本地通过不冒充真实故障或自然记忆验收。Z16/Z17与Epic保持开放，production_ready=false。剩余副本责任见RETAINED_COPIES.md。
