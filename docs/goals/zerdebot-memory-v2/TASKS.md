# 任务看板

[GitHub Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157)。状态来源：task_manifest.json。代码、部署和产品验收分开记录；当前所有实现尚未部署。Z10 的生产清零、Z11 的真实模型和七天试运行仍未执行。

| ID | GitHub | 依赖 | 状态 / PR |
|---|---|---|---|
| Z01 | [#158 FIX: 停用自动互动并隔离旧记忆路径](https://github.com/Bayashat/zerde-serverless-bot/issues/158) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/180) |
| Z02 | [#159 FIX: 日志脱敏和 Telegram 内容最小化](https://github.com/Bayashat/zerde-serverless-bot/issues/159) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/177) |
| Z03 | [#160 FIX: 旧记忆删除与业务数据边界](https://github.com/Bayashat/zerde-serverless-bot/issues/160) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/182) |
| Z04 | [#161 FIX: 统一部署配置和可复现打包](https://github.com/Bayashat/zerde-serverless-bot/issues/161) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/183) |
| Z05 | [#162 FEATURE: Memory V2 身份、事实和控制契约](https://github.com/Bayashat/zerde-serverless-bot/issues/162) | Z01, Z04 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/186) |
| Z06 | [#163 FEATURE: 可靠消息摄取与后台恢复](https://github.com/Bayashat/zerde-serverless-bot/issues/163) | Z05, Z13 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/190)；[集成#192](https://github.com/Bayashat/zerde-serverless-bot/pull/192) |
| Z07 | [#164 FEATURE: 明确自述抽取与个人和群档案](https://github.com/Bayashat/zerde-serverless-bot/issues/164) | Z06 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/188) |
| Z08 | [#165 FEATURE: 有来源的记忆问答与预算控制](https://github.com/Bayashat/zerde-serverless-bot/issues/165) | Z07 | implementing |
| Z09 | [#166 FEATURE: 更正、遗忘、退出与来源编辑闭环](https://github.com/Bayashat/zerde-serverless-bot/issues/166) | Z05, Z08 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/191) |
| Z10 | [#167 FIX: 旧记忆清零工具和切换演练](https://github.com/Bayashat/zerde-serverless-bot/issues/167) | Z01, Z03, Z09 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/195) |
| Z11 | [#168 FEATURE: 多语言评估、单群试运行与推广](https://github.com/Bayashat/zerde-serverless-bot/issues/168) | Z02, Z04, Z08, Z09, Z10, Z17, Z19 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/196) |
| Z12 | [#169 FIX: 验证码状态竞争与失败恢复](https://github.com/Bayashat/zerde-serverless-bot/issues/169) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/179) |
| Z13 | [#170 FIX: 反垃圾执行结果和重试语义](https://github.com/Bayashat/zerde-serverless-bot/issues/170) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/185) |
| Z14 | [#171 FIX: Voteban 会话身份和逻辑过期](https://github.com/Bayashat/zerde-serverless-bot/issues/171) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/189) |
| Z15 | [#172 FIX: 新闻抓取时限与分群交付恢复](https://github.com/Bayashat/zerde-serverless-bot/issues/172) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/193)；[集成#197](https://github.com/Bayashat/zerde-serverless-bot/pull/197) |
| Z16 | [#173 FIX: Quiz 发布、计分与答案恢复](https://github.com/Bayashat/zerde-serverless-bot/issues/173) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/194)；[集成#197](https://github.com/Bayashat/zerde-serverless-bot/pull/197) |
| Z17 | [#174 FEATURE: 成本归因、dev 按需运行与有效告警](https://github.com/Bayashat/zerde-serverless-bot/issues/174) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/187) |
| Z18 | [#175 CHORE: 旧 AWS 资源清理清单与执行手册](https://github.com/Bayashat/zerde-serverless-bot/issues/175) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/184) |
| Z19 | [#178 FIX: 抽奖事务的 DynamoDB 序列化边界](https://github.com/Bayashat/zerde-serverless-bot/issues/178) | 无 | pr_open / [PR](https://github.com/Bayashat/zerde-serverless-bot/pull/181) |
