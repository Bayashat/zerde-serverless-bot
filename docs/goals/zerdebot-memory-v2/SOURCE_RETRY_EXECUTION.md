# F4：来源独立重试与无记忆回答边界

状态：PRE 已 ALIGNED，现有 owner 内已实现，POST/correctness/维护性已 ALIGNED，整仓 2331 项和 hooks 通过；CI、合并、发布及重新实测待执行。延续已批准的质量修复目标；F3 原始报告、语料、费用和判定文件保持不变。

Goal / Intent：一条来源的错误抽取不拖住同批已正确处理的来源；本次没有提供记忆时，回答不推断数据库为空，也不承诺自行搜索消息历史。

Truth owner：现有 `memory_v2/extractor.py` 解析和重试；`FactWriter` 仍是唯一事实写入入口；`group_agent.answer_group_question` 继续拥有无记忆回答提示。

Contract boundary：全批 envelope、候选、完整 JSON、来源索引完整性必须先全部校验。只有明确绑定来源后的 facts 校验错误才转该来源的 `defer`；同一来源任一事实非法，整条来源不提交部分事实。合法空 facts 可完成。未知实现异常不得被当作部分成功。

Cutover / Displaced path：原来的全批 facts 一处失败即重复全批，替换为按不可变 ref 保存完整成功结果，并只在第二次调用请求未完成来源；局部 source_index 重新编号，结果按 ref 回到原顺序。保持每次 extract_batch 最多两次模型调用，不能另开按来源重试循环。

每次尝试仍依次验证来源/租约、检查预算、占日配额、预留费用、再次验证来源、调用和结算。第二次请求、验证和映射只针对待处理来源。预算、配额、transport、结算或 schema 失败均保留此前完整成功结果，未完成项沿既有恢复入口 defer。当前调用返回完整结果后，worker 对每个来源再次验证并由 writer 原子提交；来源/租约校验异常和进程取消仍向上失败并允许以后重做，不承诺跨调用永不重问。没有来源校验豁免、无新账本或 writer。

无记忆提示只表述本次请求未提供长期记忆和历史搜索工具；不能由此声称已存数据不存在、用户未说过或资料被清空，不能承诺自己查历史。可以说明当前无法核实并请用户提供当前消息或引文。现有 Gemini 及备用模型共用该提示；当前离线 plain serializer 也调用 group_agent 的同一纯提示函数，严格 wire 等值检查原样保留，消除原先复制提示的漂移；不读旧记忆，不加人物/问题关键词规则，不把提示约束当作真实模型保证。

Acceptance evidence：复现 mixed-009 形状，证明坏称呼来源保持 PENDING、正常语气来源和空事实来源完成；第二次只有待处理 ref，顺序/局部编号正确，二次成功能完成原来源。覆盖一个来源多事实的原子拒绝、全 envelope/index 错误不部分接纳、二次 budget/quota/transport/settlement/schema 失败仍保留已完成结果、源编辑/租约失效不写入、总调用上限不变。公开回答路径验证主备 provider 均收到准确能力提示。独审、全套测试、CI、实际产物读回分别记录；真实质量要在新冻结会话重新验证。

Kill / Forbidden：不得规则生成称呼、放宽证据/敏感/身份/引用边界、增加两次调用上限、改变 gold/scorer/语义审阅策略、覆盖旧运行或重置累计费用，不启用学习、不恢复旧记忆/抽奖/自动社交、不改云资源或数据。

| Task | Owner / 输入 | 允许文件 | 禁止文件 | 输出 / 依赖 |
| --- | --- | --- | --- | --- |
| 研究 | aws_audit，只读 F3 故障与现有 owner | 私有研究记录 | 产品源码/历史运行 | 接口、租约及预算风险 |
| PRE | code_audit，本文与研究 | 审查意见 | 实现 | ALIGNED 或明确修订；实现之前 |
| 实现 | root，已审契约 | extractor、group_agent、当前 plain serializer、相关测试与文档 | 冻结 source/run/gold/账本/infra | 确定性回归与整仓验证 |
| POST / 维护性 | code_audit / memory_audit | 审查意见与证据 | 实现 | 独立 ALIGNED，修复阻断项 |
| 交付 / 验证 | root / aws_audit | scoped PR、发布回执和执行入口 | 新 epoch、旧路径 | CI、精确合并、dev/prod 产物读回；新模型会话另行冻结 |

整仓首轮揭示离线 plain serializer 复制旧提示造成 5 项失败；小增量 PRE ALIGNED 后收敛到原 group_agent owner 的纯构建函数，未放宽 validator、audit、gold 或 scorer，历史冻结源码不动。此类 serializer 同步是当前实现的一部分，不是对旧评估补分。

本地最终 [验证与独审收据](evidence/2026-09-19-f3/f4-verification.safe.json)绑定修复源码；首轮失败日志保留。不同范围的专项测试不相加，真实模型质量仍未通过。
