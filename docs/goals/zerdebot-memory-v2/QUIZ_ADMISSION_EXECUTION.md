# Quiz 调用准入与恢复修订契约（2026-09-29）

状态：本切片已由PR232合并并完成dev/prod实际发布、主/独审和预算reader重绑；[发布证据](evidence/2026-09-29-quiz-admission/release.safe.json)。真实异常恢复仍待[R3下一契约](R3_QUIZ_ADMISSION_RECOVERY.md)，不以本地或发布检查替代。

## 目标与边界

Goal/Intent：计数依赖故障不能被解释成允许调用；每一次应用发起的 Gemini 尝试都准入一次。对用户如实说明权限与终态核验。Truth owner：原 QuizRateLimitRepository 的 PT 日期主键与 publication 恢复 owner；观察日志不是预算/账本。Cutover：替换原失败返回(0,True)/错误读0/循环外一次准入；不留开关或第二路径。

禁止改 Memory 计费/UNKNOWN/epoch/控制、表/队列/IAM/基础设施/SDK版本/模型选择/支付、当前数据或旧冻结报告；不启用新功能/群/prod记忆。保留原真实超限和供应商错误的 fallback 顺序、现有生成权限、管理员对账与 DONE 无写语义。

## 单一计数实现：强读校验后条件 CAS

保持 increment_and_check()->(int,bool) 和 get_today_count()->int；本地失败统一 QuizQuotaUnavailable，不继承模型错误。每次准入选择 PT 当日固定键，ConsistentRead=True，只有响应为dict且完全不含Item才视为缺整行。存在空/非dict行、缺 count 或数字非法皆拒绝。只接受非布尔 int 或有限非负且数学上为整数的 Decimal。

唯一写入算法：最多3次 CAS 竞争尝试。缺整行时用 attribute_not_exists(PK) 条件创建 count1；已有合法计数则用 request_count=:old 条件SET为old+1。保留48小时TTL与原key/limit。只对明确 ConditionalCheckFailedException 有界重读；其它连接/限流/超时/不完整返回一律失败，不能靠重读回推此前未写。UPDATED_NEW 必须包含等于目标的新合法计数才给许可。坏行零写；并发冲突不覆盖其它调用；未知落库不退款/清零/手写许可。超过limit仍保留递增后判定的原口径，故计数不是发送次数或账单。客户端潜在重试/未知写也不补账。

只读缺行0；失败抛同异常。get_rpd_status将不可用映为(None,total)，不显示满额。历史日键/计数不重置或回填，切换时间写发布证据，不增加epoch。

## 每次调用与恢复

Gemini显式循环每次网络前先同owner准入。SDK HttpRetryOptions(attempts=1)，锁定1.65.0；原默认本就是1，不能称此前SDK已隐式多次重试。交互2次/定时4次上限、超时/退避维持。第二次准入失败时不发第二次请求；有效超限仍按原fallback，依赖失败禁止fallback。

QuizGenerator.generate_question和translate_question在宽except前re-raise同一QuizQuotaUnavailable。QuizService只在准备调用周围捕获它，调用原mark_publication_failed(execution, unknown=False, reason="quota_unavailable")；真实原状态仍GENERATING，lease_until=0，原事务保留同request/generation/intent与outbox，并非新增FAILED状态。返回status=error、retryable=true。不得进入PREPARED/SENDING/发送题目。此状态落库也失败或不明则向外失败并保留原租约/outbox，绝不制造完成。不要覆盖prepare_publication/Telegram发送异常边界。

daily不能换分类继续模型调用，翻译不能吞此错误再发英文题；真正供应商失败仍保留原题库降级/分类轮换。无需模型的题库路径不增加全局准入检查。原恢复任务按原身份重试，不能造新恢复owner。

## 安全的尝试观察

在原两个provider类调用点，每个真实应用HTTP尝试开始创建uuid attempt_id和单调时间；结束沿同id记录provider/model、结果分类、耗时、可信HTTP状态、实际返回input/output/total tokens。最小不采集provider request id，不增加publication参数链，不声称可按publication精确账单归因。

共用小型纯观察helper（services/provider_observation.py）只归一字段并安全写日志，不写存储、不准入、不发网络。usage区分known/missing/invalid/no_response；缺字段为null、不补0、不推算total，拒bool/小数/负数。日志或usage解析异常不丢有效题/重试网络；start无终态保持未知。503/传输错误/坏响应的费用未知，不推断免费。

替代本次provider错误body、str(error)、响应preview与Generator异常链日志；保留共享redactor，不重构全仓日志。API映射使用固定安全分类，from None避免原正文进异常链；JSON错误固定文字；fallback只记error_type。Generator验证日志只记topic长度、错误值类型和泄题词数量，不输出topic/任意模型值/泄题原词。未知非API异常仍按原异常路径上抛由Generator记录类型并失败，不能因新观察而扩张付费fallback。用最终formatter验证合成prompt/token/body不出现。日志是观察证据，不能当完整供应商账本。

## 文案

四语言help移除不存在的ADMIN_USER_ID限制；现行群成员/genquiz策略不变。quiz_reconcile_ok改为“已核对现有题目及其计分记录。”等中性对应语言，DONE无需发题/写分数。保留权限拒绝/原生Reply/ownbot/poll版本匹配。

## 顺序看板

| Task | Owner | 允许文件 / 输入 | 输出与证据 | 依赖 / 并行 |
|---|---|---|---|---|
| PRE | 独立reviewer | 本契约、当前源码、旧三份研究 | ALIGNED或具体修订 | 实施前；只读可并行 |
| 实施 | 主代理 | rate_limit_repository.py、llm_provider.py、provider_observation.py、quiz_generator.py、quiz_service.py、bot/core/translations.py | 单一CAS准入、错误恢复、安全观察 | PRE；串行 |
| 检验 | 主代理/独立reviewer | 聚焦Quiz/provider/recovery测试、相关既有混合测试 | 针对性+完整tests/hooks；POST/正确性/维护性审阅 | 实施后 |
| 发布 | 主代理/独立verifier | 新冻结候选、实际ARM包、两env配置保护与精确changeset；既有发布结构重新适配 | CI、dev后prod五函数ZIP/层/依赖/配置独立读回 | 审阅后；不可并行发布 |
| 同步 | 主代理 | PLAN/TASKS/HANDOFF/EVIDENCE/manifest、Z16/Z17/Z02与Epic | 真实阶段状态、GitHub读回、自动任务更新 | 每次实质交付 |

## 有意义的验收

1. 本地Moto模拟的Dynamo条件语义测试（非真实AWS并发或传播验收）：缺整行、坏行零写、Decimal合法/小数/NaN/负值/bool、并发limit-1最多一个许可、冲突3次耗尽、连接/限流/AccessDenied/写响应丢失/坏返回拒绝、PT边界不删旧键。
2. Gemini两次503/成功每次先准入；第二次超额/失败不发，失败不fallback而有效超额fallback；锁定SDK用本地HTTP mock证实单attempt，不调用外网。只读额度错误为未知。
3. 真Generator+原Service/Repository组合：daily首分类或bank翻译依赖失败后无后续生成/英文发送，原GENERATING+outbox保留；同generation恢复一次DONE；状态写失败不伪造成功；普通provider翻译失败原降级保持。
4. 兼容供应商和Gemini正常/503/传输/坏JSON的安全attempt及usage未知；有效响应usage坏字段或logger失败仍返回题、网络只一次。格式化日志和异常链不含合成敏感正文。
5. 非admin原genquiz与管理员对账拒绝保持；四语言提示；已DONE不写不发沿现有测试，不复跑旧线上题目。全量tests/hooks及真实ARM五入口验包；Memory五计费owner字节不变。

## 发布、退出与独立恢复试验

不改变基础设施/配置，仅代码包；新候选冻结前核实际基线五函数/层/保护项及原控制，主检/独审。dev后prod发布必须核实际ZIP全部源码/依赖与保护配置，记录新代码发布时间及旧Quiz最长300秒在途过渡窗口，窗口未结束前不声称全部调用采用新口径；新整包后重绑预算只读reader，即使Memory owner字节未变。CI/源码通过不是线上故障恢复已通过。

如本地失败则不发布。如dev新错误则停prod推广，不继续发测试，保留业务租约/outbox/计数/UNKNOWN并优先修复前滚；不在未设计停发措施时回退旧fail-open来绕过准入。任何额外停发配置/回滚必须另作精确作用与恢复契约并独审，不在本契约中宣称已有可用开关。

真实dev故障注入单独阶段，不在本源码修订时写IAM/计数或造失败。需另审具体role/policy/LeadingKeys/作用所有dev当日Quiz的影响、短窗口、传播验证、恢复期限与实际恢复步骤；宽泛测试授权已有，无须重问，但契约缺失不能直接动作。禁LambdaInvoke、伪造update/阈值/成员、Receive/Purge混合队列。普通真实验收用新的专用群公开命令，旧2397/2398/对账永不重跑。线上UNKNOWN/GSI/daily并发未实证继续OPEN，production_ready=false。
