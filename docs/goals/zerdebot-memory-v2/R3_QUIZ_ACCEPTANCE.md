## 2026-09-30最新交付：Quiz持久请求反馈

PR235已合并并部署dev/prod：原请求确认保留后提示后台继续尝试且无需重发；处理中、待核对、过期和无效请求分别说明；提示发送或诊断失败不再重试整次出题。实际sendMessage异常日志仅记录类型。原publication/outbox/准入与计分所有者不变。

2334全测、两项CI、两环境五入口ARM及实际五函数/共享层的主检和独审通过，300秒窗口后配置稳定。实际只更新Quiz，其他四函数和层保持；104文件费用闭包逐字不变，预算读取器已重新绑定并时点PASS。运行构建源`7d3f42827662cae428bc3276319a165add9c417a`，merge`6a5acf160092a30b6b718135b11ac4ccb6feb38c`；部署workflow ACTIVE。

新版反馈的真实Telegram补验、daily并发、发送UNKNOWN到DONE、答案先到/GSI迟到及其他失败重投仍未覆盖；不以本地测试或发布成功关闭Z16。其余R3业务/实际费用继续，自然0/50有据、0/20未知，production_ready=false。

[本轮发布证据](evidence/2026-09-30-quiz-feedback/release.safe.json)；[实现契约](QUIZ_FEEDBACK_EXECUTION.md)。此前受控恢复与旧轮次均已结束，本轮没有新发题、模型测试、资源删除或新群/生产记忆启用；副本责任保持[原台账](RETAINED_COPIES.md)。

## 2026-09-30：真实受控准入失败已自动恢复

一次真实dev公开发题在受控准入失败后保留原GENERATING/outbox；撤销临时限制后，同request/generation自动成为DONE并出现一个真实poll。执行记录创建至完成289秒，后续正常恢复cursor再次推进且题目/poll不变、outbox缺席；主检与独立读回通过。原角色策略、函数配置和Memory控制保持，临时policy已提前撤销并在固定窗口结束后再次确认不存在。

本次仅通过一个受控准入失败恢复及有限窗口不重复，不覆盖daily并发、发送UNKNOWN、GSI迟到、其他失败重投或自然记忆质量。后续PR235已修正已保留请求的反馈；继续原Z16及其他R3业务/费用验收；Z16/Z17保持OPEN，production_ready=false。

[本轮脱敏证据](evidence/2026-09-30-r3-admission-recovery/result.safe.json)。本轮没有新Lambda发布、新群/生产记忆启用或付款变更；该受控恢复验收当时运行构建为PR232的`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，现运行基线以上方PR235记录为准。19项主工具及22项独立工具本地检查只验证操作器，真实结果由本轮原生操作、持久记录和独立云读回证明。

## 此前发布记录：2026-09-30 Quiz准入修订

PR232已合并并部署到dev/prod：原Quiz计数强读与条件CAS、每次Gemini应用重试准入、计数错误穿透生成/翻译并保留原GENERATING/outbox恢复，安全attempt/usage观察及四语言帮助/对账提示已交付。2306测试、两项CI、两环境五handler ARM及实际五函数/共享层主检和独审通过；实际更新Bot、Memory Worker、Quiz三份函数代码，News/Operations/层沿用已核实际包。

运行构建源`0c6529d5c33b9afdf1229c559c83f961f04bc03f`，merge`4fda918ab5e5a8f4b65e349c9d6cfb6902d40181`；两环境300秒窗口后的配置重读通过，workflow ACTIVE，新104文件预算reader时点PASS（非持续许可或账单）。[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；[下一验收契约](R3_QUIZ_ADMISSION_RECOVERY.md)。本节记录PR232发布时点；后续受控恢复结果以上方最新记录为准。

# R3真实Quiz正常链路与终态对账（2026-09-29）

9月28日完成Z16的一次正常公开流程，9月29日增加一次DONE终态公开对账；以下前两节记录9月28日，Z16仍OPEN。9月28/29日验收时运行构建源保持`01bdc1da2c5d995759eda0dfef99f7b427301d60`；没有部署、资源删除、新群/生产记忆启用或支付变更。

## 9月28日已发生的动作与结果

唯一获准dev测试群内，已授权测试账号在原生Telegram发送一次`/genquiz@zerde_dev_bot Python easy ru`，收到俄语Python原生Quiz，实际选择一次`list.append()`。UI显示一票与正确选择。随后以该群唯一当时请求的实际身份强一致读回，确认：

- 发布执行DONE；发布记录、poll映射与执行拥有相同poll及generation。
- 答案由真实poll_answer持久化为SCORED；账号/群/题对应，答对计1分，总分从无记录的0到1，answer_revision为1。
- 按现有on-demand规则，weekly_points与week_score均0；只有daily题计周榜，不能把0误报为丢分。
- 精确publication与answer outbox均缺席。执行创建到完成2秒，答案received与completed同一整秒；这是记录时间，不是端到端p95。

UI视觉第一项与Telegram实际option_id分别为0和1；按选项文本和持久化选项映射核对，不能按画面位次推算协议ID。当前成功只有一次答案，未据此证明重投不会重复加分。

私有消息、poll/用户标识及原始AV均只存本机0600文件；公开结果仅聚合与证据hash。右键菜单未取得原生消息链接，改用仅目标群REQUEST分区的一次强一致Query找实际标识，再精确GetItem；未Scan、未读其他群。未声称点击过这次题目的来源链接。

## 9月28日预检、费用与已发现的说明问题

五个dev函数CodeSha/Revision/config与已验证S4发布匹配；权限/webhook/当日Quiz计数及恢复规则读回仅证明配置，不冒称实际失败恢复。原restricted成员形状和并发null形状两次校验器误停回执保留，最终实际成员可发言、并发未预留；未更改角色或并发来制造成功。

现解析器使用空格分隔，逗号会进入topic并丢失明确easy参数；当前正确命令如上，支持kk/zh/ru。原历史报告保留，最新入口覆盖旧逗号示例。当时帮助翻译错误限定ADMIN_USER_ID；该差异已由PR232修正，现有获准群成员权限不变。

Quiz当日RPD从缺行（原语义0）到1；它统计外层Gemini生成请求，不覆盖全部SDK重试及DeepSeek/Groq备用调用，数据库计数错误还有原fail-open路径。故不作为实际供应商调用总数、模型费用硬上限或Memory预算许可。真实账单归属仍由Z17跟踪，未改任何原费用owner、UNKNOWN或付款设置。

## 2026-09-29：管理员对已有DONE题目的原生Reply对账

群主在同一专用群原生Reply昨日已结束且一票的原始dev题目，发送一次公开quizreconcile，使用既有强读记录中的真实request key和generation。机器人返回成功。原execution仍DONE、poll/generation不变、原答案仍SCORED、总分1和周分0不变，两个outbox仍缺席，当天PT计数键仍缺席。八行前后逐值相同，独立八次实际强读再次确认；顺序读取不冒充事务快照。

原生Reply锚点和成功文字由主代理在UI见证；独审负责数据库读回，没有再发命令。新命令和响应的消息ID未从UI取得，不填推测值。UI未出现新poll，没有新的投票动作。这是一次DONE终态对账幂等证据，不能推断UNKNOWN恢复、失败重投或无界并发都成功。[本轮证据](evidence/2026-09-29-r3-quiz-reconcile/result.safe.json)。

成功提示实际写“恢复其计分记录”，而DONE分支仅核验后返回，无恢复写入。该文字与genquiz帮助错误限定管理员已在PR232修正：保持现有权限策略，明确生成命令对获准群成员开放；对账仍仅本群管理员，成功提示只能表达实际已核对的结果。不得为了匹配提示而新增计分写入。

本轮没有新模型生成、部署、Memory控制/预算owner写入或付款变更；当日RPD前后为空只说明该精确计数键没变化，不等于所有供应商的整日用量为零。独立预检确认旧Q与S4的环境hash取值投影不同，实际配置未漂移；保留原误停回执与新绑定通过回执。

## 继续执行

上述帮助/提示、计数失败与安全可观测性已由PR232完成CI、实际包发布及保护主检/独审。[R3受控准入恢复契约](R3_QUIZ_ADMISSION_RECOVERY.md)已完成本轮限定验收，操作器和请求冻结，不重跑。后续PR235已修正反馈；继续按原Z16契约分别取得并发daily、发送不明及reconcile、答案先到/lookup延迟、其他数据库失败与重投幂等证据。任何尚未发生的分支标为未覆盖；不得伪造update、直接写答案/分数/阈值，或为验收手动Lambda Invoke、Receive/Purge混合队列。

已完成的限定验收不会关闭Z16，也不会增加Memory自然样本；自然起点仍未建立，0/50有据、0/20未知，production_ready=false。继续Z01/Z02及Z12–Z17独立工作，备份期限保持[原台账](RETAINED_COPIES.md)。


## Quiz准入修订交付（2026-09-30）

PR232已完成dev/prod实际发布、两环境五函数/层主检与独审、窗口后稳定读回及新预算reader绑定。原RPD强读/CAS、每次应用重试准入、错误穿透、原outbox恢复、安全attempt/usage与四语言文案已交付。完整2306测试和双job CI通过；本次没有新增发题、模型测试或故障注入。真实daily并发、UNKNOWN恢复、GSI迟到及失败重投仍待，不以发布成功替代。

[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)；[实现契约](QUIZ_ADMISSION_EXECUTION.md)；[冻结本地证据](evidence/2026-09-29-quiz-admission/local.safe.json)。
