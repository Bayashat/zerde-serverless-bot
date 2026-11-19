# /wtf handoff

`/wtf` 已部署 dev `@zerde_dev_bot`，等待用户在 Telegram 自行测试；prod 未发布。使用 `/wtf 宝马M系列`，或回复一条人类消息发送 `/wtf`。采用群配置语言，媒体沿用现有显式路径；嘴毒解释限定2–4短句。

源提交 `0aa67e318218cd163955bf349b51821bf708a08b`。GitHub PR #306 保持待review，Issue #305 跟踪用户验收及后续prod。代码CI三job通过（2845检查、5个ARM handler）。本次末尾仅文档/安全回执提交跳过重复CI，运行源码与已验证提交逐字节相同。

发布采用 live-template 代码专用 CloudFormation changeset，实际仅 dev Bot/MemoryWorker 的 Code.S3Key 改变。不要用现有默认整栈workflow重发本功能：预览发现 dev runtime变量/群配置与live漂移，会停运行及改变告警；本次没有修改这些配置。prod须用户测试反馈后按fresh production模板另备代码专用发布并独审，不能直接运行dev操作器或照搬dev模板。

主读回两实际ZIP hash与候选一致、各96份源码精确相同，10函数配置保持、其他8函数代码保持，stack UPDATE_COMPLETE，完整模板与候选严格相同。ZIP仅源码和依赖，无Telegram/模型输出采集；没有主动调用真实模型或Telegram。实际语气/有用性仍由用户现场测试。

原主工作区其他Nov19验收及副本台账未提交修改未带入本次；旧Memory V2任务、自然样本和raw保留责任保持。已执行部署器冻结保留于本机 build/wtf-release，不作重跑入口。
