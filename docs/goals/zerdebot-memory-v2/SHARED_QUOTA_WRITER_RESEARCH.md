# 共享 Gemini quota writer 有限源码研究

状态：**DRAFT_RESEARCH_NOT_PLAN_PRE_NOT_IMPLEMENTED**

## 结论与证据范围

建议另立一个最小 writer 修复切片。两个明确源码缺口仍在：存在的日计数行缺字段会被静默初始化；有限非整数/负数等坏计数先被写增量，再经 `int()` 转换，消费端可能接收表面合法的正整数。PR248 已修复三个消费者之一的结果门禁，但没有修写入 owner，这与原 EXPLICIT_QUOTA_GUARD 排除范围一致。本研究没有读取实际云行，**未证明 dev/prod 当前存在坏行、发生越额或计费差错**。

健康非负整数行的更新表达式在 DynamoDB 单项内原子执行；源码没有先读后无条件写的竞态。因此不能仅凭缺并发测试就声称当前正常行会丢增量或重复授予最后一个许可。文档对“永不 double-count or drift”的绝对承诺过强：本接口无逻辑 attempt ID，且共享 boto3 resource 未在此显式限定 SDK 重试；SDK/网络不明结果及重投不是严格一次计量证明。本次不推断线上 retry mode 或具体重试次数。

仅离线读取源码、测试和既有安全契约，比较 Git blob；0 测试执行、0 AWS/GitHub 网络、0 UI/Telegram/模型/账本动作、0 产品修改。不运行任何旧 once，不更改冻结报告或保留期台账。本文件仅新安全研究，无业务原文副本。

## 绑定

- 本地读取 HEAD：`d6c5f4e64d0298b483cb1d2db30f185d04046a10`；父代理已刷新 origin/main：`d6c5f4e64d0298b483cb1d2db30f185d04046a10`。
- 当前运行构建源按既有交付为 PR248：`8f1ba52960d8fe1b551dcdfe3e104b9d06ef04a0`；本轮不重新证明线上包。
- 下列13个实现文件已独立用 `git show` 核对：工作树 = 指定 origin/main = PR248 构建源字节。文档 main 不是新的运行包。
- 原合同：`.codex/AGENTS.md`、`docs/goals/zerdebot-memory-v2/EXPLICIT_QUOTA_GUARD.md`（当前及原范围）、`issues/Z17.md`；历史仅指针，不重跑。

## 具体可证路径

### 1. 存在但缺字段的行获得新许可

`src/bot/services/repositories/rate_limit.py:77–95` 对 `stat_key=RATE#gemini_generate#<PT日期>` 无条件执行：

```text
SET request_count = if_not_exists(request_count, :zero) + :inc, ttl = :ttl
```

此处区分的是属性是否存在，不是整行是否存在。若当天行存在但无 `request_count`，会把计数写为1并更新 TTL，随后 `(1, True)`（在配置额度至少1时）能通过所有消费者。它把未知存量状态重新起算；不是仅允许新日期整行不存在时合法初始化。

### 2. 坏数写后转换能穿过 PR248

同文件93行 `int(resp["Attributes"]["request_count"])` 在完成写入后才转换，无有限/非负/整值验证。

- DynamoDB 支持的有限小数：旧 `Decimal('0.5')` 写成1.5，再返回整型1；旧4.5、额度5时写成5.5，再返回 `(5, True)`。这是源码表达式/Python数值语义推导，非本轮执行用例或现场行证据。
- 旧负整数-1会先写成0，消费者拒绝0；下一次再写成1并可放行。拒绝第一次没有保全原坏行，也没有避免后续静默“恢复”。
- 字符串/布尔旧属性不能直接作 DynamoDB 数字加法；正常服务应返回错误，不能把 `int('1')`/`int(True)` 说成这类存量行实际获准路径。若写响应本身畸形，当前转换同样没有严格类型门禁，这属于响应防御缺口。
- NaN/Infinity不是可正常存入的 DynamoDB Number；可作本地输入/响应负控，不能称线上已存在。

### 3. 依赖失败在现有调用者处已关闭，不能重复宣称 PR248 未修

`ClientError` 在 writer 89–91行仍记录异常并返回 `(0, True)`。计数器写入是否已发生可能不明，但三个生产消费者都拒绝此 sentinel，当前没有因它继续新的 Gemini 网络的源码路径。非 ClientError（例如超时）直接穿透：显式链不把它归到 provider fallback，两个 Memory 消费者捕获为不可用/延后。问题重点是被 writer 转成合法正整数的坏状态，而不是再次实现 PR248。

失败时不减回、不清零、不补写历史次数。当前 `get_today_count` 97–109行把缺属性/ClientError/类型错误视作0，也会截断Decimal；但全仓 Python 调用扫描未发现共享类此方法的生产调用者。Quiz 的同名方法是另一类。它是待明确的接口边界，不能把它伪造成目前第四条放行链；最小切片不必为未调用展示接口另造工程。

## 全部直接消费者与计费所有权

| 生产消费者 | 实际构造/调用与当前保护 | 计费边界 |
| --- | --- | --- |
| `GeminiClient.group_chat_reply` | `gemini_client.py:183,286–295`；真正正整数 + 真 bool；`group_agent.py:171–223` 每次应用重试重新调用该方法，只捕获原 provider 类，配额不明不走此 fallback | 普通显式 Gemini 的共享 PT 日次数；`_post_generate_content:203` 的 HTTP `retries=False`。不是 Memory USD 预留 |
| `MemoryExtractor._extract_eligible` | `extractor.py:176,228–259`；每应用尝试先 budget.check_available，再同一 quota，再严格结果，再 budget.reserve，再源核验/模型 | `memory_worker_main.py:109–114` 实际构造，默认同共享 RATE key；原 Memory 财务 reservation/settle 仍须通过 |
| `MemoryAnswerSelector.select` | `answer_selector.py:67,74–85`；每次先 budget.check_available，再同一 quota，count真正正整数且 allowed is True，再 reserve | `public_answers.py:143–146` 实际构造；Memory 选择预算不被共享次数代替 |

全仓 `RateLimitRepository`/`increment_and_check`/`get_today_count` 的 Python 引用扫描只找到上述三处共享类生产构造与三处增量调用；`repositories/__init__.py`只是重导出。三处均未传自定义 scope/limit，因此使用环境内同 stats 表 `RATE#gemini_generate#PT日期`。默认 GEMINI_RPD_LIMIT 由配置提供，dev/prod分别在自身表中；不是跨环境/跨供应商全局账单。

Quiz `src/quiz/services/rate_limit_repository.py:30–93` 是独立 owner：Quiz表 `PK=QUIZ_GEMINI_RPD#PT日期, SK=LATEST`、`QUIZ_LLM_RPD`。它已有强读、缺整行与坏字段区分、有限非负 Decimal/真int校验、最多3轮条件更新、精确响应验证。`llm_provider.py:103–119` 每次应用尝试准入，google SDK显式 attempts=1。可参考这些局部语义，**不共享/迁移它的 key、counter或异常 owner，不用Quiz测试证明共享writer安全**。

原 Memory 五计费核心文件保持：`memory_budget.py`（MODEL/CONTROL/ATTEMPT、reserve/settle）、`memory_v2/_cost_catalog.py`、`_cost_state.py`、`cost_monitor.py`、`cost_meter.py`。预算表是独立V2表，UTC月/原epoch/DAY/UNKNOWN不等于stats表PT日次数。三处都可能在真正模型网络前因后续预算/源栅栏失败而消耗一次准入；超过RPD的被拒尝试当前也递增。因此共享counter是保守准入尝试计数，不是已发送模型请求/真实token/实付。`repositories/_common.py`在获取 resource 时注册原 `cost_meter.register_client`；未来若为局部SDK边界换client，必须仍走原计量hook，不修改/绕过费用owner。

## 现有测试覆盖（仅阅读，未重跑）

- `tests/test_explicit_quota_guard.py:37–53`：唯一直接使用共享真实 repository 的新场景是模拟 UpdateItem ClientError，验证0模型/0备用/0send。56–124其余返回矩阵、第二次准入失败、异常保持及合法成功/耗尽正控，注入的是**repository输出**；不是存量坏行实写测试。
- `tests/test_memory_v2_extraction.py:426–444`：PT午夜耗尽、(0,True)/(1001,False)/(True,True)不调用模型/不reserve；quota是替身。
- `tests/test_memory_answer_budget.py:150–157`：sentinel阻止选择及预算；其它预算/重试测试保留原reservation责任，不能替代共享writer数值校验。
- `tests/test_quiz_admission.py:36–132` 有缺行/缺字段/非整数/负数/NaN防御、有效Decimal与最后许可并发、有限冲突、读写错误、已写响应不明责任；仅属于Quiz独立owner。
- 本次全仓测试引用检索未找到共享 `rate_limit.py` 健康行/坏行不可变、最后许可并发、不明写响应后的不授予/不退款定向覆盖。既有2375全测结果是历史整轮结果，不因本研究成为新通过。

## 建议的最小新切片（研究建议，须另立计划和 PRE）

1. 原共享 `RateLimitRepository`继续唯一写入。只在整行不存在时初始化；已存在行的 count 必须为真int或有限非负整值Decimal，转换前验证。不默默纠正缺字段/负数/小数，不改它们和TTL。
2. 沿原 key/日期/limit/TTL和“每次保守准入尝试递增”的语义，以强读加精确条件写入保护验证与更新之间的竞争：缺整行条件 `attribute_not_exists(stat_key)`；有效旧值用精确前值条件；不要 read后无条件update。可参考Quiz有限3轮CAS，只对已确认条件冲突进行有限重读；首次真实成功后验证返回计数与预期一致。
3. 故障/畸形响应/竞争用完提供不能被误当耗尽或供应商失败的 unavailable，三个消费者保持现有拒绝/延后/不fallback语义。失联或结果不明立即停止本次准入，不应用级重发、不减计数、不重置UNKNOWN。单次逻辑调用与SDK重发的边界需在正式计划明确：当前resource无局部retry约束；若引入CAS，不应把可能由隐式SDK重发形成的条件失败误当纯并发冲突来再次消费。选择局部单尝试配置时保留cost_meter注册，不改全局共享client策略/五费用owner。
4. 有限验证只覆盖该writer及三消费者：缺整行正控、合法0/正整数Decimal、存在但缺字段和坏类型/小数/负数保持字节与TTL、返回畸形/失联即无新模型和无退款、两个竞争者争最后许可/不丢增量、条件冲突有限上限、PT日期/TTL不变、三真实消费编排的sentinel/异常/合法耗尽对照。断言不把次数称成wire或实付。无需新群、线上造坏行、真实模型或已冻结F5–F10重跑。
5. 仅 `rate_limit.py`及直接必要的局部依赖/测试/文档候选；PR248消费端防线保留。Quiz/News/Operations/Memory五费用文件与旧账本不改，不复制新钱包或迁移owner。若依现有发布结构更新Bot/Worker共同包，按原规范独审、定向/全测/CI/实际包读回及当前budget reader重绑；这些都是未来条件，**本报告不是实现或发布结果**。

修复有必要的依据是两项具体写入缺口，而不是要求证明历史全量未发生任何计数误差。底层共享writer修改是原PR248明确排除的独立新切片，不能追写旧报告称当时已修。

## 实现字节清单

| 路径 | SHA256 |
| --- | --- |
| `src/bot/services/repositories/rate_limit.py` | `a54e2edc974cddb203aa60030c9d82ce1e71afd74cc6af5c2957c616c4023baa` |
| `src/bot/services/repositories/_common.py` | `ca954fffee84e7df69833a6c20cff2f37e1df3615df54b10e33e8137482ec7b3` |
| `src/bot/services/ai/gemini_client.py` | `b8c6dc6708979e251d5e8b1dae0de353f7ebc03edf8ae08641cc83dc1d7196de` |
| `src/bot/services/group_agent.py` | `42f29e41976199736e89168909b6df822a4d1adf70f06b563f52a07100c450dc` |
| `src/bot/services/memory_v2/extractor.py` | `6aa9fcac649b5ab24e5ac699443c866097c2700f18d44e2535cad1a7bf4db963` |
| `src/bot/services/memory_v2/answer_selector.py` | `2f0fff7742367d769977e9a88c6887821e99815d85db0bc8f8d3ee54fd4ac8ec` |
| `src/quiz/services/rate_limit_repository.py` | `969ebf510de1789baf3366556d0a99ccc0d04ab4ca106531a1da1cc0afa10267` |
| `src/quiz/services/llm_provider.py` | `d95f3559447ba83fe3610ed1f9d9209bf1af57af3e6a4b3922c31f9edae93955` |
| `src/bot/services/memory_budget.py` | `cafa84db20cb6d17858cedd01ff72e42c4229a56992673ff2a3e1fb7974df9cb` |
| `src/bot/services/memory_v2/_cost_catalog.py` | `fa10173174d88bfae5e304f4b9ccaadfacc434f7f77c13c7674d4948a0eded63` |
| `src/bot/services/memory_v2/_cost_state.py` | `5e603965627c64a06a11e83b6c632059712c745dc9683883dc2e84c98c981e69` |
| `src/bot/services/memory_v2/cost_monitor.py` | `e238592c2db06b03c97b2c44baa99f0fb396f7557d2c23acbdcd827bb2aa8ea7` |
| `src/bot/services/memory_v2/cost_meter.py` | `4d34b49a01948ff7423629591093d3af611a8dcfd0be77efc1dc637bd7cdd0ca` |

研究生成 UTC：2026-10-09T07:58:51.004255+00:00。

## 追加：最小兼容选择与 SDK 歧义边界（仍仅研究）

### 默认和非默认 scope

共享构造函数37–40行允许非默认 `scope` 和显式 `rpd_limit`；方法63行还允许单次 scope 覆盖。`_limit_for_scope`55–58行：同实例scope使用该实例limit，不同scope则查询 `_SCOPE_LIMITS` 或回到配置 `GEMINI_RPD_LIMIT`。当前 `_SCOPE_LIMITS` 只有 `gemini_generate`。仓库生产调用者三处全部无参构造/无参增量，因此没有证据证明当前使用其它scope；不能删掉既有scope API或把它们混进默认key。正式切片可保留现有key/limit选择，并有限测试一例非默认覆盖防回归，不把全部未使用scope当新增业务验收。

共享 `get_today_count` 无生产调用；Quiz `GeminiQuizProvider.get_rpd_status`使用的是Quiz独立类，不能混淆。

### 返回 sentinel 与 typed 异常的兼容结论

最小外部行为兼容方案是保留当前 ClientError 的 `(0, True)` sentinel，新增“坏行/无可信响应/冲突用尽”也可返回这个不可靠结果；它不是permit，三个消费者都已先验证计数并拒绝。这样显式链仍由 PR248 产生原 `GeminiQuotaUnavailableError`，抽取仍变 `daily_quota_unavailable`，选择仍变 `AnswerSelectionUnavailable`。新增 writer 专属异常也能阻断调用，但会改变显式链观察到的异常类型，因此不是维持原已验收边界的最小选择。

具体捕获：`gemini_client.py:286` 的 owner 调用在解包 try 外，新的 typed writer 异常不会被转换成 `GeminiQuotaUnavailableError`；`group_agent.py:192–223` 不会将这种 RuntimeError 归 provider重试/回退；在真实 `ExplicitDelivery` 场景，外层906–909行日志后重抛。`extractor.py:237–246` 捕获任意Exception延后；`answer_selector.py:76–85` 捕获任意Exception再转固定 `AnswerSelectionUnavailable`。因此 typed 不是错误选择，但需额外显式兼容合同/测试，不能写成“完全保持原异常类型”。

既有非 ClientError owner 异常穿透语义也应优先保持，而不是为了统一个新异常把所有旧异常重新分类。新的本地校验失败可用明确 unavailable sentinel；对于读取/写入的不明异常，无论保留穿透还是同sentinel，都不得再调用writer/模型/备用路径。上层当前硬门禁继续保留，不退回仅检查 within_limit。

### 不改共享 SDK 的更小 CAS 重试门禁

主代理提出的边界可采用：只有真实 `ClientError` 的精确 `Error.Code == ConditionalCheckFailedException`，且 `ResponseMetadata`为dict、`type(RetryAttempts) is int`、值严格0，才能视作本次SDK逻辑调用没有内部重试的纯条件冲突，再进行下一轮强读/CAS（总共最多3轮）。缺字段、True/False、非整数、负数或非0都不是已知纯冲突，停止并保留可能已写增量。不能为缺metadata填0。

本地锁定 boto3/botocore版本1.42.38（uv.lock），当前venv的botocore同版本。`botocore/endpoint.py:192–227`显示每次网络重试attempts递增，结束时在解析ResponseMetadata写 `RetryAttempts=attempts-1`；`httpsession.py:466–470`下层 urllib3 显式 `Retry(False)`。这是本地同版本源码依据，不是本轮线上client/session配置或线上重试次数观察。

如此可保留 `_common.get_dynamodb`和原cost_meter hook，无需改变共享SDK策略，也避免一次CAS首写已成功但响应遗失、SDK重试条件失败后应用再推进一次的计量偏移。成功只有返回的正确数值和本轮预期next一致才能授予；失败或响应不明不读后“补发”、不退款、不清UNKNOWN。至少新增“ConditionalCheckFailed＋RetryAttempts=1/缺失/True”不重写，以及明确0时有限三轮的负/正控。成功响应重试元数据不是允许重放的条件；不要声称CAS天然严格每网络/应用恰好一次。

### 注释准确性

`rate_limit.py:6`仍写single UpdateItem with ADD，实际80行是SET算术表达式；两者并非同一表达式。健康计数下原子更新成立；本研究未证正常整数并发故障。新切片应只校正该局部注释与保守准入含义，不能用新增CAS宣称修复了已观测线上竞态。
