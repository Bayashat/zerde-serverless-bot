# 下一受控 dev Quiz 准入失败执行契约

状态：本次契约已执行并结束，主检/独审通过限定的准入恢复及有限窗不重复；所有once、原生请求和临时policy操作均冻结，不得重跑。以下为原执行边界，实际结果见[脱敏证据](evidence/2026-09-30-r3-admission-recovery/result.safe.json)。依据当前PR232源码及[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；研究原稿、首次归因修订与最终边界独审均冻结保留。真实identity/固定窗口和19项本地检查已冻结留证；本文件不是下一次执行许可。

目标：一次新的、真实的专用dev群公开genquiz请求，在真实准入依赖失败时留在原publication/outbox，撤销故障后由原业务链将同request/generation自动恢复成一个真实poll，有限复查窗不重复。此为业务受控合成验收，Z16/Z17仍OPEN，自然样本不增加；不验收UNKNOWN/GSI/daily并发/所有重投或完整费用。

唯一owner仍原QuizRPD、publication/outbox和现有恢复规则。不得手写业务状态、重置RPD、伪造Update/成员/答案，操作人不得Invoke Lambda、Receive/Purge混合队列、停恢复规则或修改lease。Creature/群主仅在已授权Test bots，$ake限制不绕过；不重发2397、不答2398、不重复既有reconcile。

## 先满足门槛再准备操作器

PR232两env最终主/独审、窗口后稳定读回、workflow ACTIVE及新budget reader绑定全部完成。新鲜绑定实际source/包/层/配置、专用role的RoleId/ARN、表TableId、原inline/attached策略集合及边界、现有恢复规则/目标/权限。有限区域role消费者全枚举并标明范围；已知复用即停止重审。原RPD强读缺行或合法计数且有保守空间；不修改额度。原outbox强读必须完整分页，达到上限未穷尽即停止，不能把指标零或空列表当无并发保证。

精确注入仅为dev Quiz角色、新唯一名称、dev表、当前PT日RPD分区、UpdateItem的内联Deny；沿研究中的LeadingKeys+Null=false+CurrentTime条件，不能限定SK、群或请求。它可能影响该窗口其它dev生成/翻译/恢复，必须先向用户说明该范围；其它已知在途则推迟，窗口出现其它请求则撤销并降级归因。不改变原default policy、环境/并发、规则、表/队列、模型或prod。

冻结新唯一intent：RoleId、完整policy JSON/hash、T0、T1=T0+300秒、PT日、policy名字及原集合hash。日界前后至少15分钟，不延长窗口；唯一真实命令须位于窗口早段且剩余至少120秒。最大Put一次，写前先有能独立运行的精确撤销工具及本地看护。Put响应不明仅精确读同名policy，不重Put、换名或延长T1。读回身份/内容不符即停。模拟矩阵只证明配置语义，不证明IAM传播或具体服务拒绝。

新工具主审/独审须落实API和资源白名单、时间/identity/文件hash、独立撤销入口、UNKNOWN分支及停止逻辑，然后才可实际注入。现合同没有实际时间或policy名字，不可直接执行。用户已有授权，不新增重复许可门槛。

## 真实证据与恢复

记录唯一原生公开命令和真实Telegram消息ID后绑定REQUEST；不得猜ID或手补字段。失败捕获采用 execution→outbox→execution 强一致夹读：两次execution的generation/revision/state/lease及受保护投影一致；状态GENERATING/reason quota_unavailable/lease0，outbox同generation/next_attempt_at0。变化中可短时有界重读，未捕到稳定失败态则不算该门槛通过。随后request题目行缺席及UI无poll仅证明观察窗；可能出现正常失败文字。

失败态RPD前后逐AV比较，原quota/UNKNOWN不改。成功后的计数/attempt/usage按实记录，不预定只能一次模型调用，不拿缺日志当零费用。准入在SDK网络前终止由源码与应用链支持；若无服务商直接证据，不宣称供应商零调用/零费用。

取得失败证据立即精确撤销唯一临时policy：先核同RoleId、正文/hash，再Delete，只删本轮对象；NoSuchEntity可为缺席完成，正文/身份不符不盲删。Delete不明先读，允许有界同身份删除重试。T1自动终止新增Deny授权效果，不等于policy对象删除或保证恢复时刻；意外退出/网络失败仍保留后续对象清理责任和真实延误。

不再发命令/Invoke/reconcile，仅等待原业务链。直接验收同request/generation/intent成为DONE，同generation题目行和实际poll META一致、outbox缺席、UI一个真实poll。原调度规则/目标输入、cursor变化、唯一公开请求、状态推进与时间窗仅支持恢复来源推断；现入口日志没有action，不能声称直接捕获某次EventBridge recover_publications投递或手补日志字段。若既有独立数据事件可直证则另列，否则明确未直证。具体AccessDenied服务码也未直证，不增加新observer/日志owner。

至少覆盖下一次实际恢复机会：有界枚举/读取原恢复cursor推进、已启用规则与调用窗口/指标，保存其观察依据，随后夹读同DONE/poll/outbox缺席并独审。只睡五分钟不算已证明二次机会；无法关联时限定报告为有限观察窗无重复，缺口继续开放。日志未追平或有其它请求不据此宣称窗口独占，不把全部provider usage归给该请求。

故障捕获阶段意外进入SENDING，视为未命中或状态不符；撤销后的恢复阶段允许租约内正常的短暂SENDING，只读等待原owner进入DONE，不为正常发送瞬态误判失败。T1后15分钟仍未DONE，或发送结果不明、租约过期后UNKNOWN、持久化错误、其它请求、超范围影响，即停止预期成功判定、精确撤销并保存真实状态，继续原恢复诊断，不造第二命令/失败或释放UNKNOWN。最终核role及原policy集合恢复、函数/控制不漂移，独立读回并核UI证据所属。四副本期限、Memory owner/epoch/DAY/UNKNOWN保持。

验收最高结论仅为“原业务链对同request/generation的真实准入失败自动恢复及有限窗不重复”；单次成功不升级为整个Z16、自然质量或生产推广完成。
