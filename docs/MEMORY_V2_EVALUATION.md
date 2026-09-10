# Memory V2 离线评估与证据边界（Z11）

关联 [Z11 #168](https://github.com/Bayashat/zerde-serverless-bot/issues/168)、[Epic #157](https://github.com/Bayashat/zerde-serverless-bot/issues/157) 和 [批准计划](goals/zerdebot-memory-v2/PLAN.md)。

本 slice 提供开发工具、合成 gold 语料和评分器，不改变 Lambda、记忆读写 owner、旧路径退役状态或部署配置。产品状态仍为 **IMPLEMENTED_UNPROVEN**；真实模型、dev canary、生产群试运行都未执行。不能据此关闭 Z11 的真实验收部分。

## 语料与标签

`tests/fixtures/memory_v2_eval/scenarios.jsonl` 是静态、可版本控制的 JSONL，`CATALOG.md` 是其人工可读目录。全部消息、Telegram ID、业务行摘要均为合成数据，AI 编写；不含导入群历史。每条记录明确 `synthetic: true`、`authorship: ai_authored`、`independent_review: PENDING`。独立代码 review 与逐条语言/事实标签复核是不同证据，不能互相替代。标记 `REVIEWED` 必须附 `review_reference`，不额外要求用户亲自审核。

当前包含 **240 个多轮场景、516 个唯一事实标注、256 个未知问题**。kk、ru、en、mixed 各 60 场景、129 个事实、64 个未知问题。唯一事实按 `(scenario_id, fact_id)` 计数，重复 checkpoint 不增加语料事实数；指标另明确计算 checkpoint 事实观测分母。

`corpus_authoring.py` 保存语言文本库和可复核的确定性编排：每种语言 20 个不同个人上下文，另有 40 个时序、身份或故障分支。不同语言间有意保留对齐场景，便于比较；它们不是 240 份独立收集的真人对话。混语场景在同一对话中切换语言。所有 240 个完整消息/操作序列均不同。未知问题询问该成员没有自述过的公开字段，并不把缺失结果当作拒答。

覆盖本人明确自述、引用、转发、同名异 ID、同 ID 异群、单值替换、多值撤销、旧来源晚到、同秒歧义编辑、空/敏感编辑、暂停时编辑、provider 失败和恢复、预算暂停、30 天 pending 过期、原文到期后的最小证据、180 天 last-confirmed、旧 epoch 重放、forget 后新学习、optout/optin、群删除范围、管理员群规则确认、历史消息激活边界及 bot 输出。证据为原文 **Python 字符索引** `[start:end]`，不是 UTF-16 偏移或模型生成的引用文本；未来 Telegram adapter 必须先转换偏移。

这是一份可审阅的初始合成语料，仍需要独立标签复核及真实 provider 观测。自然语言等价表达可通过 gold 的 `accepted_values` 明确加入；不能根据被测模型的输出自动扩充正确答案。名称、大小写和空白使用 NFKC/casefold/空白归一化。单值时效标签也必须一致，不能把 last-confirmed 算作当前事实。

## 本地命令

在仓库根目录，使用锁定的 Python 3.13 环境：

```bash
uv sync --frozen --python 3.13
uv run --frozen python -m dev.tools.memory_eval validate
uv run --frozen python -m dev.tools.memory_eval self-check --output /tmp/zerde-memory-eval-selfcheck
uv run --frozen python -m dev.tools.memory_eval evaluate \
  --predictions /tmp/observations.jsonl \
  --provenance /tmp/provenance.json \
  --output /tmp/zerde-memory-eval-observed
uv run --frozen pytest tests/test_memory_eval.py -q
```

`self-check` 显式使用 `OracleSelfCheck` 复制 gold，只验证评分器记账；其输出永远是 `provider_kind=synthetic_oracle`、`model_quality_claim=NOT_VERIFIED`。`evaluate` 必须给独立观测文件，绝不自动补 gold。所有内置 CLI 均只读写本地文件，没有网络、供应商调用或任意模块加载选项。重新编排语料可运行 `python -m dev.tools.memory_eval.corpus_authoring`，必须审阅生成 diff 和新 SHA256。

`validate` 结构或数量失败返回非零；`evaluate`/`self-check` 返回 0 只表示所提供文件的数值门槛满足，不是上线批准或真实模型通过。JSONL 重复属性、NaN/Infinity、重复 checkpoint/问答 ID、未来证据及缺失业务保护快照会拒绝；未知字段不会被当作安全断言，预测自报的 `violations: 0` 完全不参与评分。

## 观测契约和唯一 owner

评分器是观察者，不是新的记忆写入路径。`ObservationAdapter.observe_scenario(scenario) -> list[dict]` 为以后接入真实本地域对象的接口；Z06 摄取、Z05 FactWriter、Z08 检索/预算、Z09 生命周期仍拥有各自状态。当前只内置 oracle；尚未实现完整 Z08/Z09 场景 replay adapter。

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

`traces.business_before/after` 要给固定的 `CONTEST#23`、`SETTINGS`、`CONTEST_TTL_OUTBOX` 键及测试域 owner 读回的规范摘要。评分器将其与 gold 的合成保护快照比较；不是依赖被测程序自报“业务保留”。真实本域 replay adapter 需要将固定 fixture 映射到实际实体并规范化摘要，不能直接复制 gold 作为业务成功证据。

`safety_surfaces` 必须分别提供 `raw/context/logs/answers` 四类边界捕获的完整文本列表，缺任何一类都不会把敏感泄漏判为零。评分器扫描合成秘密标记（大小写归一化）和明确 unsafe 源文本，同时检查每条断言的来源；这是一组已标注风险的检测，不能替代对任意自然语言所有潜在敏感信息的独立审核。空列表只表示该边界实际没有文本，不得为了获得零错误而省略捕获。

`sent_actions` 来自边界 fake Telegram 客户端实际调用记录；空列表意味着确实观察到没有发送，缺字段意味着未验证。`work` 来自持久行读回，必须有唯一稳定 `work_id` 和状态 `PENDING/LEASED/DONE/EXPIRED/FAILED/PAUSED`。同一任务多 checkpoint 只按最后快照计一次覆盖率；不要用每次重试次数充当不同任务数。正常/恢复成功行可带 `lane=normal|recovery`、`elapsed_seconds`；待处理行可带 `age_seconds`。文本问答延迟用 `ask_text_seconds`，不包含多模态承诺。`cost.usd` 是该 checkpoint 新发生的成本，不得重复累加累计快照；报告标注 `SUPPLIED_TRACE_UNVERIFIED`，不等同于真实 AWS/供应商账单。

来源文件可声明 `provider_kind=fake_provider|recorded_provider|synthetic_oracle|unverified_observations`，并附模型、运行时间、请求 trace 摘要和独立复核引用。这个标签只是证据来源描述，评分器不会把 `recorded_provider` 字符串当作真实性认证。真实 trace 应存于受控位置，公共仓库只留脱敏引用和摘要。

## 指标和缺口

- 每种语言分别给 TP、FP、FN 与分母；事实 precision 至少 95%，明确自述 recall 至少 90%。事实值正确但引用错误不会混成语义值错误，而会单独降低来源支持率并触发相应安全门槛。
- 来源支持必须 100%：作者/chat 必须与原始事件一致，证据必须完整覆盖 gold 支持跨度，不能引用被编辑、删除、optout、旧 epoch 或有歧义的来源；引用段、forward、bot、激活前消息、未确认群规则不能提供有效证据。
- 未知问题必须实际返回 `abstained=true` 且无任何断言，至少 95%；缺问答、已知事实答非所问、或“拒答但仍断言”不能算成功。另报告已知问题的完整回答比例，防止只衡量未知拒答而忽视正常问答能力。
- 错误归属、跨群、敏感信息、删除后复活、业务损伤、自动社交各自独立计数。来源/操作元数据与保护快照参与推导；缺原始来源或缺必要 trace 是 `UNVERIFIED`，不是零。单个断言可能违反多个边界，计数不是唯一受影响用户数。
- 只有 DONE 且有合法耗时的记录进入学习延迟。正常 p95 上限 300 秒，恢复 600 秒，文本 ask 15 秒；暂停、失败、过期不能拿 0 秒填入。延迟无样本为 `UNVERIFIED`。覆盖率列出 paused/expired、待处理最大年龄与观测 checkpoint 数；采样文件本身是否完整仍需来源证据。

`numeric_thresholds_pass` 仅指语言质量和零容忍数值，不包含真实 provenance、真实标签复核、延迟/成本采样充分性、dev 或 pilot。延迟每项独立列 PASS/FAIL/UNVERIFIED；不能用本字段替代整份上线门槛。所有输出固定 `product_gate=IMPLEMENTED_UNPROVEN`、`model_quality_claim=NOT_VERIFIED`。

后续真实验收顺序仍为：独立 gold 标签复核和真实 provider trace → dev 合成群完整业务验收 → 单群至少 7 天、至少 50 有证据问答及 20 未知问答 → 按 PLAN 决定推广和旧并行代码退役。样本不足保持未验证；本 slice 没有启动任何试运行，也没有调用真实模型、AWS 或 Telegram。
