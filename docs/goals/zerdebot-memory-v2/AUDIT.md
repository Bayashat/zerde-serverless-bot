# ZerdeBot 审阅快照（2026-09-10）

此文件是历史审计结果，不代表后续实时状态。基线 main `2f3abe7f9f19d390c2253fc24722af9db521cd17`。只读 AWS/代码审阅，无云修改、数据删除或 secret 正文输出。

## 已确认缺陷与源码入口

| 问题 | 基线入口 | 后续工单 |
|---|---|---|
| 正则 profile 将引述工作经历当本人事实，住所变更并存；profile/recent 存在隐私过滤旁路 | services/repositories/group_memory.py:846,1089；services/memory_safety.py:186 | Z05-Z09 |
| forget group 整分区、forget me 通用 user_id 匹配会误删 contest/settings | repositories/group_memory.py:585,2066 | Z03/Z10 |
| memory worker 不检查开关/源项/epoch，向量 status 回写可重建残项 | group_memory_processor.py:540；repositories/group_memory.py:1537 | Z01/Z06/Z09 |
| 源项消失仍使用向量 candidate；清理无持久重试 | memory_retrieval.py:414；vector_memory.py:296；handlers/commands.py:837 | Z01/Z09/Z10 |
| 完整 Update 在白名单前日志；网络错误可能含 token | webhook.py:85；telegram.py:105；shared logger.py:13 | Z02 |
| captcha 先解限再保存，错误被吞，timeout 可误踢；创建/读失败无可靠恢复 | handlers/captcha.py:99,153,257；repositories/captcha.py:75,101 | Z12 |
| ban 失败仍计成功，voteban 无 session/到期条件 | spam/enforcer.py:48；repositories/votes.py:66,110 | Z13/Z14 |
| news 慢源超总时限；scheduled 失败正常返回；quiz 发布冲突及 GSI lookup 延迟丢答案 | news/services/digest.py:236,334；quiz/services/quiz_service.py:602；bot/repositories/quiz.py:34 | Z15/Z16 |
| workflow 缺类型化 retention 等 mapping；部署依赖未与测试锁统一；告警无通知动作 | infra/stack.py:114；deploy.yml:117；observability.py | Z04/Z17 |

源码路径以上按 src/bot/services 为默认；PR 应刷新精确当前行号。已有 593 tests 全通过，额外 fault injection 说明覆盖缺口。

结构结论：保留现有 Python/Lambda/SQS/DynamoDB，拆业务职责与统一事实生命周期；不做整仓语言/框架重写。contest 的事务决定和 outbox 恢复可供其他业务借鉴。顶层 core/services 包名冲突、巨大模块是维护建议，不是已证实生产故障。

## 全账号账单（USD）

Cost Explorer 窗口 2026-06-01 至 2026-09-11（结束日期排他），9 月10日查询，9月 estimated。

| 月 | Usage | Credit | Tax | Net |
|---|---:|---:|---:|---:|
| 06 | 12.4540467891 | -12.4540470233 | 0 | 约0 |
| 07 | 32.9198326169 | -32.9198329741 | 0 | 约0 |
| 08 | 19.3048745148 | -9.27 | 1.60 | 11.6348745148 |
| 09 MTD | 5.1869952598 | 0 | 0.83 | 6.0169952598 |

这是账号费用，不是 Zerde 实付，也不证明已支付。Project/Environment/CloudFormation cost allocation tags 全 Inactive，resource-level cost data 未启用；账号含其他项目，外部 Gemini/Groq/DeepSeek 费用不在 AWS 表中。

FreeTier actual：Lambda 339178.504375/400000 GB-s，201748/1000000 requests；SQS API 显示100万封顶，但 CE 实际1697402 requests、$0.2789608；X-Ray 94856/100000；日志2.0891851/5GB。预测均账号级，不能当项目未来账单。

Zerde 28 alarms（dev/prod各14）整月目录毛价$2.80，实际共享额度无法分摊。2026-08-11至09-10 15:30UTC：dev main/vector sent/received均0，empty receives分别661734/397051，合计1058785，按$0.40/百万约$0.4235；prod main/vector空接收662106/396213。Main/vector max concurrency=10/3 禁用部分低流量poll优化，production vector 限流仍保护provider，不直接移除。

Frankfurt S3 Vectors usage：6月$0.3090941860、7月$0.0020395128、8月$0.0032757053、9月MTD$0.0064524052。目前区域仅Zerde两bucket，历史逐资源归因未启用，不能声称已证明历史全部属于Zerde。

## 资源范围与候选

全部17个启用region检查CloudFormation及Lambda/DDB/SQS/Logs/HTTP API/EventBridge/S3Vectors的项目名称；其余16region×7类=112次枚举无匹配。名称不含项目标识的资源仍不能穷尽归属。当前dev/prod stacks均UPDATE_COMPLETE，各4Lambda/3DDB/4SQS/1HTTP API/1vector bucket及index/4业务log group/14alarms；prod另9EventBridge rules。

高置信旧资源都在eu-central-1：
- zerde-prod-bot-stats：12行2272B，90天读写0，非当前stack，当前Lambda无引用；PITR开、TTL关、deletion protection开。
- zerde-prod-updates-queue / zerde-prod-updates-dlq：空，无mapping/policy，90天无流量。
- 两个 TelegramBotStack-dev-LogRetention 日志组、tg-dev-receiver/worker日志组：对应Lambda不存在，存储0。
- /zerde/bot/token、/zerde/bot/webhook_secret 仅为进一步确认候选，外部消费者未穷尽。

共享CDK bucket、其他项目资源、整个dev stack均不在废弃范围。dev bot仍有72次调用。候选主要改善资源卫生，节省很小。此快照不是执行删除名单。

## Memory 数据

prod元数据全扫描：30432行，15380462bytes，6partitions，15页/1884.5RCU；未输出聊天或个人标识。

MSG8441/MEDIA_GROUP12/USER310/USERNAME227/USER_FACT430/GROUP_FACT1713/EVENT1495/JOKE1803/DAILY_SUMMARY3261/TERM12642/AGENT_REPLY85/PROACTIVE7/SETTINGS3/VECTOR_BACKFILL3。当前无CONTEST族不代表可整表删除。3044摘要明确telegram_export_import，最早2019-09-06。long-term有2019数据；MSG从2026-06-11起，TTL均到2036；USER/USERNAME均无TTL。raw/profile无统一import_run_id，混合来源不可可靠拆开。

prod vectors8250，与DDB indexed数量相同，仅计数一致，未证明key集合一致；dev为空。dev/prod raw/long-term/daily/legacy retention均3650天，AGENT_REPLY7天、PROACTIVE3天。memory/agent/vector enabled=true，ambient=false；proactive daily limit10。SSM prefix分别/dev与/prod，未读token值，不能断言token本身不同。

28 alarms动作全部为空。当前所有queues/DLQs空且alarms OK。30天prod indexer545calls/384Errors，最后错误9月4日，9月5日后无错误；不能说当前仍持续故障。prod stats/memory有PITR，quiz没有。

参考：[SQS scaling](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html)、[SQS pricing](https://aws.amazon.com/sqs/pricing/)。

## 执行补充：Z19 抽奖事务 SDK 边界

2026-09-10 两次独立 boto3 + Moto 模拟确认，Resource client 与手工 TypeSerializer 叠加导致抽奖事务双序列化并取消。先前抽奖生命周期的设计可借鉴，但实现的 SDK 层必须修复；原 MagicMock 绿测不足以证明该路径可运行。新增 https://github.com/Bayashat/zerde-serverless-bot/issues/178 独立修复，Z11 的业务保留验收依赖它。未调用 AWS 进行真实写入。

执行时补充：GitHub Dependabot API确认uv.lock存在24项open advisories。Z04纳入定向修复：Pillow12.3.0、urllib32.7.0、idna3.15、pyasn10.6.4、cryptography50.0.0、CDK2.253.0为advisory给出的最低修复版本；实际可用版本、依赖约束及运行时影响由锁解算与构建验证，不盲目全升级。
