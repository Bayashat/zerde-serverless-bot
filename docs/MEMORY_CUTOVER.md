# 旧记忆停用与 Memory V2 切换

关联 [Z01 #158](https://github.com/Bayashat/zerde-serverless-bot/issues/158)、[Z10 #167](https://github.com/Bayashat/zerde-serverless-bot/issues/167) / [Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)。本文件描述最终集成源码与操作门槛；不代表已经部署、清零旧数据或启用学习。当前状态仍为 **IMPLEMENTED_UNPROVEN**。

## 最终运行时协议

- 普通群聊和频道镜像帖不触发主动回答、主动评论或 reaction。旧消息学习、摘要、向量与 backfill 入口已退休；验证码、垃圾审核等保留业务继续由各自入口处理；实验性抽奖已从本次PR移除。
- 当前显式问答任务使用 `context_version=explicit-v2-sources-2026-09`。旧 Z01 过渡版本 `explicit-only-2026-09`、无版本和未知版本任务，均在正文处理和媒体下载前丢弃。版本匹配也不等于允许发送：当前问题还须通过原始时间、来源版本、群 epoch、请求者 generation 和发送收据校验。
- `app.get_memory_repo()` 使用 `ExplicitContextRepository`。它保留旧表中的业务 SETTINGS 能力，但 `record_agent_reply()` 不写旧 `AGENT_REPLY`，`get_agent_reply_explanation()` 不读旧回复正文。当前回答去重和发送状态由 V2 独立表中的 `ANSWER_REQUEST` / `ANSWER_LEASE` 管理。
- 相册关联迁入 V2 的 `MEDIA_ALBUM` 元数据，按消息原始时间最多保留一天。排队媒体请求发送前重新读取当前来源，最多四项；旧 `MEDIA_GROUP` 不再用于读写。文件内容、caption、文件名和模型媒体分析不会因此成为长期个人事实。
- Z01 阶段曾允许七天 `AGENT_REPLY` 和旧表 `MEDIA_GROUP`，那只是临时过渡。最终集成已经在源码中停止这些路径；**只部署早期 Z01 仍不满足清零条件**。必须核对实际部署的工件包含上述替换，而不能根据开关或本文件推断。
- 显式 `/ask`、@mention 和明确回复 bot 独立于旧学习及社交开关。记忆问答只使用本群当前有效事实和最小证据；无可靠来源表达未知。普通显式问答不恢复旧 profile、摘要、向量或旧 bot 回复正文。
- `/memory` 控制、确定性 profile、纠错、遗忘和 optout 由 V2 owner 处理。`CONTROL_COMMAND` 收据、排序记录及其他控制 tombstone 用于拒绝旧命令重放，不是应清除的聊天正文。它们不属于 Z10 旧记忆删除范围。
- 两个 SQS 路由器均拒绝旧 extraction、summary、vector/backfill、proactive、ambient 任务。混合主队列中的合法业务任务继续执行，不能为清零而 purge 整条队列。
- 历史导入 CLI 的 `--apply` 和库函数的 `dry_run=False` 仍在读取导出或创建 AWS 客户端前拒绝。旧内部算法尚存于源码供基线审阅，不代表可恢复运行；Z11 验收后的实现删除另行处理。

完整公共协议见 [运行时契约](MEMORY_V2_RUNTIME.md)，临时媒体与删除边界见该文件引用的 owner 文档。

## 三个时间点与切换顺序

用户于2026-09-11取消抽奖实验。本次源码移除抽奖命令/观察/存储和TTL恢复规则，旧两类抽奖任务无副作用消费；旧生产工件尚未因代码提交而改变。若清理退役抽奖数据，应在scope明确列出每个chat/root，并读回旧writer、规则及任务已经停止。删除白名单只覆盖这些root的规范META/参与者/规则alias/对应全局outbox，包含缺META但身份可验证的孤儿；未知shape阻止清理。当前设置、统计、验证码、预算等仍需保护。

计费起点、旧写入停止时间和学习 epoch 是不同概念，不能用同一个“启动时间”替代。

1. **首次 V2 资源部署前固定计费起点。** 两环境使用相同、经批准的 `MEMORY_COST_METERING_STARTED_AT`，覆盖首个专用表、队列等资源的部署。默认 `0` 表示尚未安排该部署，小时监控关闭、可选预算许可不可用；不能先以 `0` 部署资源，再把几天后的学习启用时间填作计费起点。计费时间不能后移来丢弃成本历史。资源部署和计费监控不创建 ACTIVE 群控制记录；学习保持 STOPPED。
2. **部署最终退休工件并停止旧写入。** 先停外部 import/backfill 客户端及旧摘要 schedule；Bot 和 vector-indexer、别名、已发布版本及其他可能写入旧表/索引的客户端均须纳入清单。禁止新事件在排空期间继续启动旧工件。记录所有工件的 revision、code hash、配置与消费路由，保持变更冻结。
3. **按实际旧工件排空。** 使用所有旧可执行目标的实际 timeout 最大值，至少覆盖审计中的旧 indexer 900 秒，再留 60 秒余量；不能把新源码的较短 timeout 当作旧调用上界。配置读回、执行证据和完整停写清单须共同证明排空，缺 CloudWatch 数据点不等于执行已结束。
4. **生成并执行 Z10 的独立旧数据清零计划。** manifest 必须晚于完整停写；严格使用已核对的旧表 ARN 和所有完全退休的旧索引 ARN。V2 表、控制收据、计费账本和其他业务表不能填入旧 scope。工具只处理显式 scope，不会自动推断哪个表是旧记忆。先预览、加密备份和验证，再在另行授权后执行；七天归档删除期限从原 manifest 时间计算，不因重试延长。
5. **按 Z11 的阶段门槛启用首个试点群。** 确认旧在线数据清零、剩余备份/日志/队列副本状态及部署读回，先完成合成评估和 dev canary，再在获准的单群试运行中由当前控制 owner 建立新的群学习 epoch / `learning_started_at`。这是每群来源接收边界，不是 AWS 计费起点。旧群 epoch 之前的消息及后来编辑不能变成新学习来源。单群至少七天、50 个有依据问答和 20 个未知问题的真实验收在此后完成；达标后才能推广，不能要求尚未启用的试点先产生七天证据，也不能提前关闭 Z11。

因此，通常的顺序是：固定计费起点并部署 V2 资源 → 最终旧写入停止与排空 → Z10 manifest/备份/清零 → Z11 合成评估和 dev canary → 单群学习试运行 → 真实验收后推广。迁移前已存在的 V2 专用资源必须保留其真实计费历史；不能通过调整这个顺序伪造零使用量。

## Z10 集成与读回门槛

[清零工具契约](https://github.com/Bayashat/zerde-serverless-bot/blob/016e2c8/docs/legacy-memory-cleanup.md) 中的 `explicit_threads_stopped_or_migrated`、`media_groups_stopped_or_migrated` 等证据字段，须由**实际部署工件**和当前路由的审阅支持。最新源码提供了所需的退休路径，不会自动将这些字段变成 true。完整 alias、consumer、旧 schedule、外部客户端和旧索引清单仍是操作前提。

Z10 只允许旧记录族及经确认的旧向量 marker，保护 SETTINGS、未知记录族和其他表。用户取消抽奖后，明确选定的退役抽奖root、参与者、规则alias及对应全局outbox可纳入独立退役scope；不会通过普通memory forget扩大删除范围。新版 `CONTROL_COMMAND`、CONTROL、SUBJECT、FACT、OBSERVATION、RAW、HEAD、ANSWER、MEDIA_ALBUM、PURGE 和费用前缀均不应进入删除清单。不能把“V2 使用相同 pk/sk 键结构”误读为它也是旧表。索引 scope 删除包括 orphan vectors，按 chat 缩小表 scope 不会缩小整个指定索引的删除范围。

工具的 plan / backup / apply 必须在同一已审阅、干净且依赖锁定的提交上执行。合并或 cherry-pick 工具后，应在最终操作提交重新生成 manifest；不能使用旧 PR 提交的 manifest 在新的集成 HEAD 上继续 apply。生产执行需要每批重新核对仍新鲜的停写、工件、资源身份和期限证据。

至少重放无版本、`explicit-only-2026-09` 和旧社交/学习任务，确认旧表与索引不被重新创建、无 Telegram 输出；再单独验证当前显式任务及合法业务任务。当前相册应只在 V2 中更新，旧回复读写应为零。对比受保护业务记录的 key/count/content digest，真实并发业务变化也必须解释，不能跳过失败而宣称保持不变。

## 恢复与未完成验收

回退构建必须保留旧任务退休、无旧回复读写以及旧记忆隔离。存储或模型故障时保留普通显式问答、必要删除/恢复控制；不得部署旧工件恢复长期记忆或自动互动。AWS 预算暂停抽取、记忆增强和可选趋势；短期来源接收、安全失效、删除与监控仍可运行并产生费用，预算不是账号硬止付。

本地测试覆盖旧/未知任务拒绝、旧回复隔离、实际 SDK 与 Moto 条件删除、受保护记录、orphan vectors、加密归档、排空证据和失败续跑。通过测试不代表生产已经清零，也不证明 Telegram 消息、日志、PITR、队列/DLQ 和本地备份等物理副本已经消失。

尚未完成：最终部署工件与配置读回、旧客户端停止和在途排空证据、生产 manifest/备份/清零、真实 Telegram 来源与显式问答验收、模型效果和七天单群试运行。Z10 输出 `online_clean_copies_pending` 与启用 V2 学习是不同阶段，不能合并为一个完成状态。
