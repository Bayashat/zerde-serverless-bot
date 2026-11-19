# Restore /wtf — 2026-11-19

Issue: https://github.com/Bayashat/zerde-serverless-bot/issues/305

用户要求恢复历史嘴毒调侃解释，dev先发布，用户在Telegram自行验收后再prod。

历史来源：5408a33 / #54 首次加入；f3bb730 / #57 多风格与SQS；f713699 / #93 移除旧解释管线。以 f713699^ 的 angry 人设为参考：疲惫的资深开发者、口语化、2–4短句、中俄哈三语、非技术话题不强行用IT比喻。当前额外保留英语帮助。

实现边界：当前commands共享显式入口 → PROCESS_GROUP_ASK可选answer_style=wtf → group_agent独立ReplyPolicy → 当前Gemini及DeepSeek/Groq备用。explicit_context拥有纯风格文案；/ask省略风格参数，原行为保持。/wtf跳过个人事实回答分支及公共实体lookup，保留事实/个人证据政策、当前上下文、媒体、预算、请求校验、成员授权及ExplicitDelivery。没有旧ExplainTaskRepository、PROCESS_EXPLAIN、旧配置/模型、存储、自动社交或基础设施变化，无删除。

必要验证：现有显式问答/投递/路由检查，以及三provider真实HTTP请求截取确认风格和个人证据政策；现有PR CI由工作流执行。不发Telegram消息，不运行模型质量测评。dev实际代码包读回与生产未变确认，用户自行验证语言和回复风格。

独立计划审查：通过，要求完整替换默认风格、producer/consumer限定wtf、禁lookup、保持旧bot答案上下文屏障。实现后再独立审查。
