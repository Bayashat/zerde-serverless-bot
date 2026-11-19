# /wtf evidence — 2026-11-19

- GitHub search_commits及本地完整历史一致：5408a33 (#54)、f3bb730 (#57)、f713699 (#93)。读取移除前 wtf_prompts.py 和 handlers/wtf.py 后恢复人设；未恢复旧仓储/旧任务/旧模型配置。
- 源提交0aa67e3：170项必要定向检查、pre-commit与5包lock导出通过，独立计划及正确性/维护审查PASS。三provider实际HTTP请求截取仅使用模拟transport，不调用真实模型。
- [源码CI](https://github.com/Bayashat/zerde-serverless-bot/actions/runs/44501433224)：三个job PASS，2845测试通过、五handler ARM导入/锁定依赖/退役模块缺席通过。
- 默认dev整栈预览包含无关 runtime关闭、群语言及告警变更，未执行。改用fresh live模板只替换两Code.S3Key；独立发布脚本复审及fresh changeset核验PASS。
- 本地候选取现役ZIP，旧96源全部与父提交相同，新96源全部与CI源码相同；恰6源码变化，其余ZIP每entry字节保持。共享layer hash保持。实际候选Bot和MemoryWorker ARM禁网导入、锁版本及14退役入口缺席通过，详见candidate.safe.json。
- 准备中两次本地停止：root依赖six.py/typing_extensions.py最初被算作项目源，后按现有first-party边界修正；复用ZipInfo导致旧包读取偏移错误，改copy后完整比对通过。两次均未云写。Changeset创建中读取停止；未IncludePropertyValues的响应含动态依赖占位，完整property响应主独均仅两Code变更，未放宽变更门。
- Code-only changeset已执行，stack UPDATE_COMPLETE。主读回实际两ZIP各96源精确匹配，SHA绑定候选；10函数配置hash保持，其余8函数代码不变（含全部prod），完整已发布CF模板等于候选。见deployment.safe.json与独立回执。
- 没有主动调用真实模型、Telegram或改变CONTROL/成员/预算/业务数据；未删除资源或raw，没有新增用户消息原文采集。用户自测效果与后续prod仍待。
