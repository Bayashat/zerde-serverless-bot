# F1/F2 执行契约（2026-09-17）

状态：F1 首审发现长源换行和空结果绕过两处缺口，下面修订版已由code_audit复审ALIGNED；F1实现已通过独立POST/correctness及maintainability；F1现已合并并通过dev/prod部署独立读回；F2离线测量已实现，详见[当前执行入口](HANDOFF.md)和[精确契约](SEMANTIC_REVIEW_CONTRACT.md)。不得把本文件当质量 PASS。沿用 FULL_EVALUATION_2026_09_16 的目标、历史分母与失败基线。

Goal / Intent：修复模型证据裁掉限定语和擅自转写称呼，保留明确自述、真实来源、预算暂停的原边界。
Truth owner：extractor 对模型输出做后置校验，FactChange.slot / 唯一 writer 保存值；不增加事实抽取规则或并行 profile。
Cutover / Displaced path：新的抽取后置校验替换只有提示的完整性要求；新提示 self-claims-v2.6。原 public-v25、gold、strict evaluator、费用和 source915 冻结不动。
Acceptance：真实失败形状的确定性回归、Quote/safety/length/name 边界、持久 writer、现有重试/defer 路径，独审和完整测试；通过这些只代表代码验证，不代表真实模型达标。
Kill / Forbidden：不放宽敏感/引用/长度，不把无法处理记成成功空提取，不增加模型重试次数、不绕预算、不对旧run恢复、不删旧失败或加gold alias，不开启学习。

## F1 具体算法

1. 沿用模型证据的精确、连续、唯一未引用子串匹配。不存在、重复、落在引用中或超过240字符仍报 MemoryInputError；绝不因后续扩展让它变为有效。
2. 当整条来源 strip 后不超过240字符，选择包含原子串的完整来源（保留原始偏移），再检查 quoted_spans、安全和240上限。短消息中的前后限定语、多句内容均不会被裁掉。扩展仅保留同源连续上下文，不修改事实值、身份、版本、时间，不宣称可以证明模型语义判断正确。
3. 取消物理行分支：整源 strip 后超过240字符，或完整范围跨越引用时，本轮暂不抽取。调用模型前按源分区为 eligible / defer，不能让返回空 facts 绕过范围检查。长源、跨行限定语、引用来源都不猜句界、不截断，也不生成个人事实。
4. 无法完整取证的源沿既有工作 owner 保留 PENDING，固定 reason=evidence_scope_unsupported，每24小时无模型复检，仍受既有工作到期控制；同批可处理的短源继续。完成结果按原 ref 顺序合并，不借用重编号前的source_index。覆盖率保留 pending/expired，绝不算DONE或从分母剔除。这是尚待改善的覆盖限制，不宣称长消息已被学习；回源、身份、自述语义仍由原owner验证。
5. 称呼 value 必须原样出现在模型原始 evidence 中，也在最终证据中；严格区分字母体系、拼写和大小写。匹配前后不能紧邻 Unicode 字母、组合符、数字、连接符或姓名连接用的连字符/撇号，避免 Ann/Joanne、Ann/Jo-Ann。这里只证明原文中有相同完整词，复合姓名的完整意图仍需模型语义与评估。
6. FactChange.slot 对 name 保留原字符（不做NFKC/大小写/空格折叠），但继续原安全、长度、姓名格式检查；禁止首尾空白。其它事实值的已有正规化不改，writer 仍是唯一持久入口。
7. 提示写明证据使用上述完整安全短来源，称呼必须逐字拷贝不转写/翻译。外部 provider 的原请求验证也执行相同范围门禁。不能用名称匹配结果自动生成个人事实。

## F2 测量边界（实现见独立契约）

旧 strict gold、scorer、原始输出及FAIL报告逐字节不改；新增独立逐项语义复核报告，下一轮首个调用前冻结policy指纹。只允许有完整证据的 education 资格/学科表达作受限逐项审阅，不加alias、不改预测、不豁免身份/证据/编辑/安全失败。所有education（包括strict正确项）都必须审，1:1匹配gold，重复、缺失、哈希漂移、冲突或UNRESOLVED均不能默认通过。

预算暂停033继续在每语言56个known问题分母内，未回答事实仍算缺答；安全降级单独报告。原合同限制的是记忆增强与模型调用，不声称预算暂停前零DB预读。独立身份、完整四语言分母、原95/90/100/95/90门槛和全部零容忍门槛保持。

## 执行板

| Task | Owner / 输入 | 可修改 | 禁止 | 输出 / 依赖 |
| --- | --- | --- | --- | --- |
| F1设计独审 | code_audit只读；以上算法及现有代码 | 仅审查意见 | 模型/云/实现 | ALIGNED或阻断项；root依意见修订后实现 |
| F1实现 | root；既有extractor/model/writer | memory_v2原owner、小型纯校验helper、相关测试/提示/文档 | frozen gold/scorer/output/账本/服务拓扑 | focused+全套验证，事实与sourceref不变 |
| F2契约 | memory_audit研究，root定稿与实现 | 新显式版本审阅契约/验证入口及测试 | 更改旧gold或strict分数、语义自评默认通过 | 哈希绑定、完整逐项分母、独立评审身份、保留原FAIL及暂停行为单列 |
| 交付 | root，code reviewer/maintainer/verifier | 当前分支PR及既有发布工具 | 未经读回即算部署、修改原run源码 | CI/实包后新会话复验，累计旧责任USD19.639943；学习继续STOPPED |
