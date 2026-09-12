# Memory V2 离线评估与证据边界（Z11）

关联 [Z11 #168](https://github.com/Bayashat/zerde-serverless-bot/issues/168)、[Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157) 和 [批准计划](goals/zerdebot-memory-v2/PLAN.md)。

本 slice 提供开发工具、合成 gold 语料和评分器，不改变 Lambda、记忆读写 owner、旧路径退役状态或部署配置。产品状态仍为 **IMPLEMENTED_UNPROVEN**；真实模型、dev canary、生产群试运行都未执行。不能据此关闭 Z11 的真实验收部分。

## 语料与标签

`tests/fixtures/memory_v2_eval/scenarios.jsonl` 是静态、可版本控制的 JSONL，`CATALOG.md` 是其人工可读目录。全部消息、Telegram ID、业务行摘要均为合成数据，AI 编写；不含导入群历史。每条记录明确 `synthetic: true`、`authorship: ai_authored`；2026-09-11 的模型调用前独立标签复核与批准已完成，冻结内容标记 `independent_review: REVIEWED` 并引用[复核记录](MEMORY_V2_GOLD_REVIEW_2026-09-11.md)。内容改变会自动回到 PENDING。独立代码 review 与逐条语言/事实标签复核是不同证据，不能互相替代。标记 `REVIEWED` 必须附 `review_reference`，不额外要求用户亲自审核。

当前包含 **240 个多轮场景、516 个唯一事实标注、256 个未知问题**。kk、ru、en、mixed 各 60 场景、129 个事实、64 个未知问题。唯一事实按 `(scenario_id, fact_id)` 计数，重复 checkpoint 不增加语料事实数；指标另明确计算 checkpoint 事实观测分母。

`corpus_authoring.py` 保存语言文本库和可复核的确定性编排：每种语言 20 个不同个人上下文，另有 40 个时序、身份或故障分支。不同语言间有意保留对齐场景，便于比较；它们不是 240 份独立收集的真人对话。混语场景在同一对话中切换语言。所有 240 个完整消息/操作序列均不同。未知问题询问该成员没有自述过的公开字段，并不把缺失结果当作拒答。

覆盖本人明确自述、引用、转发、同名异 ID、同 ID 异群、单值替换、多值撤销、旧来源晚到、同秒歧义编辑、空/敏感编辑、暂停时编辑、provider 失败和恢复、预算暂停、30 天 pending 过期、原文到期后的最小证据、180 天 last-confirmed、旧 epoch 重放、forget 后新学习、optout/optin、群删除范围、管理员群规则确认、历史消息激活边界及 bot 输出。证据为原文 **Python 字符索引** `[start:end]`，不是 UTF-16 偏移或模型生成的引用文本；未来 Telegram adapter 必须先转换偏移。

这是一份经过独立标签复核的合成语料，真实 provider 观测仍须单独执行。自然语言等价表达仅使用模型调用前批准的 41 个键/58 个固定 `accepted_values`，按实际源语言和原句限定；不能根据被测模型的输出自动扩充正确答案。名称、大小写和空白使用 NFKC/casefold/空白归一化。单值时效标签也必须一致，不能把 last-confirmed 算作当前事实。

## 本地命令

在仓库根目录，使用锁定的 Python 3.13 环境：

```bash
uv sync --frozen --python 3.13
uv run --frozen python -m dev.tools.memory_eval validate
uv run --frozen python -m dev.tools.memory_eval self-check --output /tmp/zerde-memory-eval-selfcheck
uv run --frozen python -m dev.tools.memory_eval replay \
  --provider-fixtures tests/fixtures/memory_v2_eval/provider_fixtures.jsonl \
  --output /tmp/zerde-memory-domain-replay
uv run --frozen python -m dev.tools.memory_eval evaluate \
  --predictions /tmp/observations.jsonl \
  --provenance /tmp/provenance.json \
  --output /tmp/zerde-memory-eval-observed
uv run --frozen pytest tests/test_memory_eval.py -q
```

`self-check` 显式使用 `OracleSelfCheck` 复制 gold，只验证评分器记账；其输出永远是 `provider_kind=synthetic_oracle`、`model_quality_claim=NOT_VERIFIED`。`evaluate` 必须给独立观测文件，绝不自动补 gold。`replay` 使用真实领域代码、Moto 原生 DynamoDB 事务和独立固定 provider 响应；它不调用真实供应商。上述离线 CLI 均只读写本地文件，没有真实网络或任意模块加载选项。重新编排语料可运行 `python -m dev.tools.memory_eval.corpus_authoring`，必须审阅生成 diff 和新 SHA256。

`validate` 结构或数量失败返回非零；`evaluate`/`self-check` 返回 0 只表示所提供文件的数值门槛满足，不是上线批准或真实模型通过。JSONL 重复属性、NaN/Infinity、重复 checkpoint/问答 ID、未来证据及缺失业务保护快照会拒绝；未知字段不会被当作安全断言，预测自报的 `violations: 0` 完全不参与评分。

## 观测契约和唯一 owner

评分器是观察者，不是新的记忆写入路径。`ObservationAdapter.observe_scenario(scenario) -> list[dict]` 现有两个明确实现：`OracleSelfCheck` 只校验评分器；`DomainReplayAdapter` 调用真实 `MemoryRepository`、`MemoryIngestion`、`MemoryExtractor`、`MemoryWorker`、唯一 `FactWriter`、`MemoryRecovery`、`MemoryLifecycle`、`MemoryBudgetRepository`、`MemoryAnswerSelector` 和 `MemoryAnswerService`。各模块仍拥有原本状态，没有复制一份写入算法。

执行前 `project_scenario` 只传事件、初始业务 fixture、checkpoint 位置和问题文本/身份；删除 facts、expected、supporting_fact_ids、accepted_values、requested_fields、safe、ambiguous、admin_verified、标签与期望 epoch/version。源版本和 epoch 由真实 repository 生成；旧任务重放使用第一次观测到的真实 SourceRef。事件中的 Telegram author/chat/time/quote 元数据仍是输入。直接把原始 gold 场景或混有隐藏标签的问题交给 adapter 会拒绝。

原文准入使用当前安全代码，不能靠 gold 的 safe=true 绕过。消息先 observe，再准入和异步排队；checkpoint 才运行 worker，因此 provider/budget 故障能发生在入队之后、提取之前。全部 16 种语料事件有明确 owner 操作，未知事件立即失败；同秒冲突由真实 OBSERVATION CAS 决定，不能根据 gold 的 ambiguous 标注直接删事实。管理员确认有独立 command fixture 的授权用户集合及内容，走 `confirm_group_fact` 的 `admin_confirmed` 协议，模型不写群规则。编辑确认消息保留原 `source_kind`，只推进来源版本使旧事实失效，不自动重新授权或提取。控制/确认协议错误使 replay 失败，不会作为普通拒收消息被忽略。

`provider_fixtures.jsonl` 是单独的 242 条人工可读合成响应记录，每条有原文、SHA256 和响应。`fixture_authoring.py` 只接受上述输入投影，以一个刻意有限的技术栈识别器生成固定响应；它不读取 gold，职业/兴趣等遗漏会反映为 FN。答案 fixture 只在实际候选事实里按问题字段选索引，不使用 supporting_fact_ids。该小型 fake provider 用于执行工程路径，**不是推荐的生产规则提取器，也不是语义质量验收**。重新生成固定响应不应该为了提高评分去复制 gold；替换响应后必须记录新的 fixture hash。

缺 fixture 会记录 `replay.state=UNSUPPORTED`，worker 保持可恢复状态；绝不把缺输入当成功空提取或拒答。CLI 保存实际 `observations.jsonl`、fixture/execution source hash 的 `provenance.json` 和评分报告。`execution_source_sha256` 覆盖本地 `src/bot/**/*.py`（含 budget/safety）、`src/shared/python/**/*.py`、本工具 Python 文件、`pyproject.toml` 与 `uv.lock`，另记 Python 版本；这是明确范围的源码与锁文件指纹，不是生产镜像或已安装依赖的完整证明。事实从有效 profile 读取，断言从真实发送回执引用的事实读取，拒答必须实际发送对应 unknown 文本。core 返回 GENERAL、预算阻断或没有发送时按 missing answer 记分；不能自行编造一次安全拒答。数字门槛失败时 CLI 返回 2，回放证据仍保留。

RAW 证据在实际 DynamoDB SDK 成功 `PutItem`、`UpdateItem`、`TransactWriteItems`、`BatchWriteItem` 后立即强读并累积；不会只看 checkpoint 最终行。此同步 Moto 回放中，写入后在同一 checkpoint 前 purge 的敏感正文仍能被评分器检出。捕获的合成正文仅用于本地评分，不回流到模型。SDK 写入形状或捕获链不符合契约会使回放失败；本机制不声称捕获未接入的其他 AWS 客户端或 PartiQL 写入。

本地 AWS 使用 Moto，DNS、socket connect/create_connection 都有禁止网络的 guard，任何尝试都会使回放失败。模型配额、群成员权限、Telegram send 和时间为明确注入的合成边界；模型预算 ledger、来源/事实/删除事务是实际代码。每次 drain 通过真实 `CostState` 事务写入带独立合成 inventory hash 的新鲜测量 fixture，以运行真实 AWS permit 检查，记录 `SYNTHETIC_OFFLINE_FIXTURE_NOT_AWS_MEASUREMENT`；它不覆盖 MODEL 暂停控制。模型 usage 同样来自固定 fixture，真实 budget reserve/settle 结果附在 `budget_ledger`。这些金额不代表任何真实供应商或 AWS 账单。该 driver 不替代真实 Webhook 命令解析、SPAM_CHECK 审核、Telegram 权限/HTTP、线上 AWS 事务及公共 fallback 的验收。将来真实 Gemini 的受控运行必须另接明确授权的 provider runner 并保留实际请求/usage trace，本轮没有开启付费路径。

2026-09-11 本地验证使用运行时基线 `9031c16`、Python 3.13.6：1488 项完整测试通过，81 项工具/领域专项与独立复核通过。240 场景、404 checkpoint、16 类事件全部执行，缺 fixture 与网络调用均为 0；固定响应的数值门槛为 **FAIL**：事实 recall 21.07%、来源支持 96.15%、已知问题完整回答 21/224、未知拒答 244/256，另有 16 个未发送答案。813 个实际任务最终为 DONE 797、PENDING 4、PAUSED 4、EXPIRED 8。fixture SHA256 为 `43a60d4075e59a7910f772f5a2a1f9a4dde2c2a75b460cbdcea835399007e1e3`；独立标签复核仍 PENDING，真实供应商 NOT_VERIFIED、七天试运行 NOT_RUN。包括句尾标点等严格值匹配造成的偏差也保留在报告，后续标签复核需单独记录，不能修改 fixture 来伪造通过。

每个观测 JSONL 行必须对应一个实际 checkpoint：

```json
{
  "scenario_id": "en-001",
  "checkpoint_id": "baseline",
  "facts": [
    {
      "chat_id": "-990000002000",
      "subject_id": "800002000",
      "field": "occupation",
      "facet": "",
      "value": "backend engineer",
      "evidence": {"source_event": "m1", "start": 0, "end": 29}
    }
  ],
  "answers": [],
  "traces": {
    "business_before": {},
    "business_after": {},
    "sent_actions": [],
    "work": [
      {"work_id": "source-10-v1", "state": "PAUSED", "age_seconds": 3600}
    ]
  }
}
```

这个例子刻意不完整：只有一个事实、没有问题结果、缺少保护行 hash，因此不能通过。完整观测必须包含每个 checkpoint 的完整有效事实集合和每个问题的真实结果。答案是 `{question_id, abstained: bool, assertions: [...]}`，每条断言使用同一事实与证据结构。若从自然语言回答转换，adapter/独立复核必须列出所有断言，不能遗漏不利内容；当前工具不会自动理解任意回答全文，不能仅凭一份声明 `abstained=true` 的手填文件证明真实拒答。

`traces.business_before/after` 必须包含 `SETTINGS`、`CHAT_STATS`、`CAPTCHA_PENDING` 三类现行业务记录的摘要。初始种子分别是聊天语气、计数起始时间和合成验证码用户 ID；它们不进入模型输入。Oracle 的旧观测格式直接比较这些种子，仅验证评分器记账。

真实回放声明 `business_trace_schema=2`：在独立 legacy 业务表按 `pk=CHAT#<chat>`、`sk=SETTINGS` 保存实际 `style_profile/updated_at` 行；另建真实单键 `stat_key` schema 的 stats 表，保存 `stat_key=<chat>` 的入群/验证/封禁计数和 `stat_key=captcha_pending#<chat>#<user>` 的验证码 generation、revision、消息锚点及状态。行字段对应当前 `group_memory.py`、`stats.py`、`captcha.py` 仓储；数据全部为固定合成值，不调用业务操作或 Telegram。验证码 TTL 是测试行的一部分，Moto 不运行真实后台 TTL 删除器。

回放对两张表中的实际完整行进行强一致读取并计算 SHA256，评分器从初始种子独立重建期望行和 hash。每类记录均有删除、修改既有字段、新增字段的真实 DynamoDB 故障注入测试；任何整行差异或缺失都会失败。空快照或把 V2 空表冒充业务保留不能通过。业务种子调整不改变原有语言 gold、场景事件、问题或 provider 响应。

`safety_surfaces` 必须分别提供 `raw/context/logs/answers` 四类边界捕获的完整文本列表，缺任何一类都不会把敏感泄漏判为零。评分器扫描合成秘密标记（大小写归一化）和明确 unsafe 源文本，同时检查每条断言的来源；这是一组已标注风险的检测，不能替代对任意自然语言所有潜在敏感信息的独立审核。空列表只表示该边界实际没有文本，不得为了获得零错误而省略捕获。

`sent_actions` 来自边界 fake Telegram 客户端实际调用记录；空列表意味着确实观察到没有发送，缺字段意味着未验证。`work` 来自持久行读回，必须有唯一稳定 `work_id` 和状态 `PENDING/LEASED/DONE/EXPIRED/FAILED/PAUSED`。同一任务多 checkpoint 只按最后快照计一次覆盖率；不要用每次重试次数充当不同任务数。正常/恢复成功行可带 `lane=normal|recovery`、`elapsed_seconds`；待处理行可带 `age_seconds`。文本问答延迟用 `ask_text_seconds`，不包含多模态承诺。`cost.usd` 是该 checkpoint 新发生的成本，不得重复累加累计快照；报告标注 `SUPPLIED_TRACE_UNVERIFIED`，不等同于真实 AWS/供应商账单。

回放的工作时间来自注入的逻辑时钟，不是模型真实耗时；未提供真实 ask latency/cost 时保持 UNVERIFIED/NOT_PROVIDED。删除前保存最后工作快照；若已完成 purge 且对应未完成 WORK 行强读确认不存在，归类 EXPIRED/purged 并标明依据，不能把删掉的 pending 工作永远算作待处理。原文 TTL 的物理删除仍可滞后，逻辑到期由真实读写代码验证。

来源文件可声明 `provider_kind=fake_provider|recorded_provider|synthetic_oracle|unverified_observations`，并附模型、运行时间、请求 trace 摘要和独立复核引用。这个标签只是证据来源描述，评分器不会把 `recorded_provider` 字符串当作真实性认证。真实 trace 应存于受控位置，公共仓库只留脱敏引用和摘要。

受控真实 runner 的本地 SQLite 汇总把响应可用性与费用核实分开。`responses` 和旧字段 `unknown_attempts` 仅按 RESPONSE/其他持久状态分类；RESPONSE 或 broker `ok=true` 不代表 schema、语言质量或 usage 已通过。`unverified_usage_responses` 计有响应但 usage 未核实的次数，`unknown_billing_attempts` 还包括 UNKNOWN/INFLIGHT 等未知费用尝试。`verified_token_micro_usd` 是已核实 usage 的标准价代币成本（含真实零值），`unknown_hold_micro_usd` 是未核实的完整预留；两者之和等于 `charged_upper_micro_usd`，不能将预留称为实际账单。缓存回放仍只复用原响应，不新增 HTTP、不重复计费，也不借汇总重新核实或释放历史预留。领域解析和真实账单验收保持各自独立。

## 指标和缺口

- 每种语言分别给 TP、FP、FN 与分母；事实 precision 至少 95%，明确自述 recall 至少 90%。事实值正确但引用错误不会混成语义值错误，而会单独降低来源支持率并触发相应安全门槛。
- 来源支持必须 100%：作者/chat 必须与原始事件一致，证据必须完整覆盖 gold 支持跨度（仅排除句末非语义标点，主语/否定/限定词保持），不能引用被编辑、删除、optout、旧 epoch 或有歧义的来源；引用段、forward、bot、激活前消息、未确认群规则不能提供有效证据。
- 未知问题必须实际返回 `abstained=true` 且无任何断言，至少 95%；缺问答、已知事实答非所问、或“拒答但仍断言”不能算成功。已知问题的完整回答比例 `supported_answer_recall` 每种语言至少 90%，必须未拒答且包含问题所需的全部有依据事实；未完整回答逐条列入 `diagnostics`。此项补齐原 recall 目标的测量定义，防止“profile 正确、所有问题都拒答”绕过正常问答验收，不更改 gold 标签或接受值。`complete=true` 仅表示观测齐全，质量仍可能不通过。
- 错误归属、跨群、敏感信息、删除后复活、业务损伤、自动社交各自独立计数。来源/操作元数据与保护快照参与推导；缺原始来源或缺必要 trace 是 `UNVERIFIED`，不是零。单个断言可能违反多个边界，计数不是唯一受影响用户数。
- 只有 DONE 且有合法耗时的记录进入学习延迟。正常 p95 上限 300 秒，恢复 600 秒，文本 ask 15 秒；暂停、失败、过期不能拿 0 秒填入。延迟无样本为 `UNVERIFIED`。覆盖率列出 paused/expired、待处理最大年龄与观测 checkpoint 数；采样文件本身是否完整仍需来源证据。

`numeric_thresholds_pass` 仅指语言质量和零容忍数值，不包含真实 provenance、真实标签复核、延迟/成本采样充分性、dev 或 pilot。延迟每项独立列 PASS/FAIL/UNVERIFIED；不能用本字段替代整份上线门槛。所有输出固定 `product_gate=IMPLEMENTED_UNPROVEN`、`model_quality_claim=NOT_VERIFIED`。

后续真实验收顺序仍为：独立 gold 标签复核和真实 provider trace → dev 合成群完整业务验收 → 单群至少 7 天、至少 50 有证据问答及 20 未知问答 → 按 PLAN 决定推广和旧并行代码退役。样本不足保持未验证；本 slice 没有启动任何试运行，也没有调用真实模型、AWS 或 Telegram。
