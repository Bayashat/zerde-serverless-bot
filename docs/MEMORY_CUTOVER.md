# 旧记忆停用与显式问答过渡（Z01）

关联 [#158](https://github.com/Bayashat/zerde-serverless-bot/issues/158) / [Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)。本文件描述源代码契约与发布检查；不能据此推断已经部署、清库或启用 Memory V2。

## 现在的代码行为

- 普通群聊、频道镜像帖不再排入主动回答/评论或 reaction；Webhook 不再调用旧消息学习或自动 reaction。验证码、垃圾审核、抽奖和命令仍按业务入口处理。
- `/ask`、明确 @mention、明确回复 bot 的请求独立于旧 `GROUP_MEMORY_ENABLED` / `AGENT_ENABLED` 和 SETTINGS 开关。它们使用本次请求及用户明确引用的内容，不读取旧 profile、MSG、长期事实、摘要或向量。
- 新问答队列载荷和新 `AGENT_REPLY` 都带 `context_version=explicit-only-2026-09`。这是临时显式问答协议，不是未来 V2 的 source/epoch 协议。旧/未知版本 ask 在正文与媒体处理前直接丢弃。
- 续聊只读取同群、同 bot 消息 id、版本匹配、未逻辑到期且没有旧检索来源的短期回复记录。旧回复、DDB 读取失败或过期记录不会回退到 Telegram 自带的旧 bot 正文；此时只能按当前问题回答/要求补充上下文。
- 新回复仍存七天短期连续对话信息；album 只存元数据，供显式媒体请求使用，独立于学习开关。这些记录属于未来 Z09/Z10 删除与切换范围，并非永久个人事实。
- 反垃圾 SQS 处理不再接收旧 memory repository，分类只使用该条审核任务的当前/明确引用内容。
- `/memory wrong` 与 `/agent wrong` 提示重建，不再修改旧事实。旧事实已整体排除，新的更正归 Z09。
- `/memory on/off/status/about me` 与 `/agent on/off/status` 明确提示重建状态，不能通过旧设置重开学习/社交。遗忘命令保留，但上线依赖 Z03 的业务数据边界；新版控制命令由 Z09 接管。
- 两个运行时 SQS 路由器均丢弃旧 extraction、summary、vector/backfill、proactive、ambient 任务；主队列其他业务任务仍处理，不清空混合队列。
- 历史导入 CLI 的 `--apply` 和库函数的 `dry_run=False` 在读取导出/创建 AWS 客户端前拒绝；本地只读分析仍可用。旧内部算法保留供审阅和基线测试，运行时无调用入口；Z11 验收后删除其实现。

## 发布与恢复

1. 与 Z02、Z03、Z04 集成并在 dev 做合成验证。生产部署前记录当前函数版本、混合队列任务构成及回退构建。
2. 先停外部 import/backfill 客户端与旧 summary EventBridge schedule。部署 Bot 和 vector-indexer 两个入口的同一修订；不能只部署其中一个。
3. 源代码 guard 不能撤回正在执行的旧 Lambda，也不能管住其他机器上的旧脚本。等旧 Bot 最长 300 秒、旧 indexer 最长 900 秒在途调用退出，结合实际配置读回与调用日志确认。清零前保持停旧写入状态。
4. 使用合成消息验证普通聊天/频道帖无自动输出；显式文本、图片/album 请求可用。重放旧记忆、社交和无版本 ask 载荷，确认无数据写入/发言；混入合法业务任务验证继续处理。
5. 此工单不删除在线记忆、向量、日志、备份或 PITR。Z10 在上述条件成立后生成 manifest/备份并清零；Z11 达标后才能启用 V2 epoch。
6. 回退必须使用保留本 guard 的构建，使显式问答保持可用；禁止部署旧版本来恢复长期记忆或自动互动。若新回复存储异常，应记录失败并修复，不能启用旧上下文旁路。

## 本地证据与未完成验收

`tests/test_memory_cutover.py` 注入旧/未知任务、缺失/过期/读失败/带旧来源的回复、旧检索调用失败，验证 fail-closed。现有显式媒体、上下文、业务路由回归随契约调整，旧 proactive 触发测试改验静默。

尚未完成：dev/生产部署读回、真实 Telegram 显式问答及零自动输出验收、停旧 schedule/外部客户端确认、在途排空、Z10 清零、V2 学习与七天单群试运行。所有本地测试使用合成/fake 输入，不构成真实效果证据。
