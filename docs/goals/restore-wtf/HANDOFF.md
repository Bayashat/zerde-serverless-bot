# /wtf handoff

用户2026-11-19明确确认dev效果可以，要求合并并发布prod。PR #306 已合并为 `1d5e08972b3c983d5bc2bd5a797d6717e1f46278`；功能源码与已验 `0aa67e3` 相同。dev和prod均已更新同一ZIP `487276781ddb4ada719bb6a6c5c46cd09f8e919fe0ec7866ccef279515658a63`，生产机器人 `@zerde_kz_bot`。用 `/wtf 话题` 或回复人类消息发送 `/wtf`，采用群配置语言。

既有源CI三job、2845测试与5个ARM handler通过；同ZIP/共享层未变，本轮没有重新运行功能测试、模型评测或Telegram自动测试。dev现场效果以用户确认记录；不补造prod用户语义验收或Memory自然样本。

dev历史发布用live-template代码专用CF changeset完成。prod首次CF预览列出额外IAM PolicyDocument截断签名和两个Quiz描述项，严格两Code门拒绝，未执行；保序UTF-8尝试与原body相同hash，条件PUT412停止，未新建changeset。原记录保留。

prod最终通过 `UpdateFunctionCode` 发布：两目标硬编码，fresh code/config/RevisionId逐项条件保护、Publish=False、不重取revision绕过冲突。只更新Bot和MemoryWorker代码；主读回实际两ZIP各96源及候选hash精确匹配，10配置及其他8代码保持，完整原CF模板和DisableRollback=true/termination=false保持。独立fresh结果见 `prod/independent.safe.json`。

**后续发布边界**：prod CF模板Code.S3Key仍指向上次包，实际运行代码已更新；这是明确记录的代码tracking drift，不能称CF模板已同步。现有默认整栈workflow还会引入runtime/群/告警漂移，不能直接重发或靠旧模板回滚本功能。后续需fresh核实际代码/配置，再按精确范围发布；拒绝的CF changeset与已执行操作器均不可复用。本轮不扩大范围修复部署系统。

源代码和发布安全回执见本目录及Issue #305。原主工作区其他Nov19验收和副本台账未提交内容未触碰；Memory V2、业务数据、自然样本和raw保留责任保持。没有删除资源或用户数据，没有新增聊天原文采集。
