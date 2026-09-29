# R3真实Quiz正常链路与终态对账（2026-09-29）

本轮只完成Z16的一次正常公开流程，Z16仍OPEN。运行构建源保持`01bdc1da2c5d995759eda0dfef99f7b427301d60`；没有部署、资源删除、新群/生产记忆启用或支付变更。

## 已发生的动作与结果

唯一获准dev测试群内，已授权测试账号在原生Telegram发送一次`/genquiz@zerde_dev_bot Python easy ru`，收到俄语Python原生Quiz，实际选择一次`list.append()`。UI显示一票与正确选择。随后以该群唯一当时请求的实际身份强一致读回，确认：

- 发布执行DONE；发布记录、poll映射与执行拥有相同poll及generation。
- 答案由真实poll_answer持久化为SCORED；账号/群/题对应，答对计1分，总分从无记录的0到1，answer_revision为1。
- 按现有on-demand规则，weekly_points与week_score均0；只有daily题计周榜，不能把0误报为丢分。
- 精确publication与answer outbox均缺席。执行创建到完成2秒，答案received与completed同一整秒；这是记录时间，不是端到端p95。

UI视觉第一项与Telegram实际option_id分别为0和1；按选项文本和持久化选项映射核对，不能按画面位次推算协议ID。当前成功只有一次答案，未据此证明重投不会重复加分。

私有消息、poll/用户标识及原始AV均只存本机0600文件；公开结果仅聚合与证据hash。右键菜单未取得原生消息链接，改用仅目标群REQUEST分区的一次强一致Query找实际标识，再精确GetItem；未Scan、未读其他群。未声称点击过这次题目的来源链接。

## 预检、费用与已发现的说明问题

五个dev函数CodeSha/Revision/config与已验证S4发布匹配；权限/webhook/当日Quiz计数及恢复规则读回仅证明配置，不冒称实际失败恢复。原restricted成员形状和并发null形状两次校验器误停回执保留，最终实际成员可发言、并发未预留；未更改角色或并发来制造成功。

现解析器使用空格分隔，逗号会进入topic并丢失明确easy参数；当前正确命令如上，支持kk/zh/ru。原历史报告保留，最新入口覆盖旧逗号示例。帮助翻译仍声称仅ADMIN_USER_ID可生成，但现行handler对获准群成员开放；列为Z16剩余修订，尚未改运行代码。

Quiz当日RPD从缺行（原语义0）到1；它统计外层Gemini生成请求，不覆盖全部SDK重试及DeepSeek/Groq备用调用，数据库计数错误还有原fail-open路径。故不作为实际供应商调用总数、模型费用硬上限或Memory预算许可。真实账单归属仍由Z17跟踪，未改任何原费用owner、UNKNOWN或付款设置。

## 2026-09-29：管理员对已有DONE题目的原生Reply对账

群主在同一专用群原生Reply昨日已结束且一票的原始dev题目，发送一次公开quizreconcile，使用既有强读记录中的真实request key和generation。机器人返回成功。原execution仍DONE、poll/generation不变、原答案仍SCORED、总分1和周分0不变，两个outbox仍缺席，当天PT计数键仍缺席。八行前后逐值相同，独立八次实际强读再次确认；顺序读取不冒充事务快照。

原生Reply锚点和成功文字由主代理在UI见证；独审负责数据库读回，没有再发命令。新命令和响应的消息ID未从UI取得，不填推测值。UI未出现新poll，没有新的投票动作。这是一次DONE终态对账幂等证据，不能推断UNKNOWN恢复、失败重投或无界并发都成功。[本轮证据](evidence/2026-09-29-r3-quiz-reconcile/result.safe.json)。

成功提示实际写“恢复其计分记录”，而DONE分支仅核验后返回，无恢复写入。该文字与genquiz帮助错误限定管理员一起进入下一修订：保持现有权限策略，明确生成命令对获准群成员开放；对账仍仅本群管理员，成功提示只能表达实际已核对的结果。不得为了匹配提示而新增计分写入。

本轮没有新模型生成、部署、Memory控制/预算owner写入或付款变更；当日RPD前后为空只说明该精确计数键没变化，不等于所有供应商的整日用量为零。独立预检确认旧Q与S4的环境hash取值投影不同，实际配置未漂移；保留原误停回执与新绑定通过回执。

## 继续执行

先修正现有帮助与行为的冲突及DONE对账的成功提示，再核对Quiz计数失败时的处理与成本可观测性。然后按原Z16契约分别取得并发daily、发送不明及reconcile、答案先到/lookup延迟、数据库失败与重投幂等证据。任何尚未发生的分支标为未覆盖；不得伪造update、直接写答案/分数/阈值，或为验收手动Lambda Invoke、Receive/Purge混合队列。

本轮普通题成功不会关闭Z16，也不会增加Memory自然样本；自然起点仍未建立，0/50有据、0/20未知，production_ready=false。继续Z01/Z02及Z12–Z17独立工作，备份期限保持[原台账](RETAINED_COPIES.md)。
