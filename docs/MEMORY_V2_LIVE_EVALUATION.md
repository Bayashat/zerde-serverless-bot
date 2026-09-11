# 受控 Gemini 合成评估

此入口只运行仓库中的合成语料，使用真实 Gemini 传输和真实本地域所有者。
它不部署，不读取真实群消息，不访问 AWS，也不向 Telegram 发消息。
原 `python -m dev.tools.memory_eval replay` 保持完全离线。

## 执行顺序与总预算

API key 只能通过 `GEMINI_API_KEY` 环境提供，不作为命令参数、配置文件或日志内容。
工具不会加载 `.env`、SSM、AWS profile 或第三方凭证。
代码独立审查完成后，由主代理执行真实请求。

先创建完整计划，只执行首个场景：

```sh
python -m dev.tools.memory_eval.live \
  --budget-usd 2 --max-calls 2672 --rpm 10 \
  --output /tmp/zerde-gemini-evaluation --stop-after-scenarios 1
```

检查首场景的真实请求、响应、归属、账本和输出后，才继续同一目录：

```sh
python -m dev.tools.memory_eval.live \
  --budget-usd 2 --max-calls 2672 --rpm 10 \
  --output /tmp/zerde-gemini-evaluation --resume
```

两个阶段共用同一个 **$2** 账本，已完成首场景不会再执行或计费。
`--stop-after-scenarios` 只是执行暂停点，不改变计划或费用上限。
部分执行仍按完整计划评分，所以 smoke 的退出码 2 表示尚未通过整体门槛；
必须检查 `progress.json` 是否确实完成首场景，不能把退出码 2 一概解释为预期。

`--scenario en-001` 可以创建独立的诊断子集，但不得把多个目录的预算当成一个总上限。
工具只接受仓库当前 `tests/fixtures/memory_v2_eval/scenarios.jsonl`，
并校验全部 `synthetic=true`、`authorship=ai_authored` 和既有 schema。
没有任意文件上传、真实 Telegram 导出导入或模型替换选项。
子集和不完整执行不能满足完整语料的尺寸门槛。

RPM 必须根据该 Google 项目实际可用配额保守设置；示例 10 不是对账户配额的保证。
并发固定为 1，间隔按已持久化的最后尝试计算，恢复和第二次尝试也受限速。
`max-calls` 限制整个运行的可能网络尝试数，不是对项目全局 RPM/TPM/RPD 的控制。
其他应用使用同一 Google 项目仍可能导致 429。

## 所有权和输入边界

`DomainReplayAdapter` 仅增加可选 `provider_factory`，默认仍创建 `FixtureProvider`。
真实模式复用原有 `MemoryRepository`、`MemoryWorker`、`MemoryExtractor`、
`FactWriter`、`MemoryLifecycle`、`MemoryAnswerService` 和答案租约。
AWS transport、时钟、成员/管理员权限、Telegram sender 都是本地合成替身。
领域进程原有的 socket 禁令保持不变，额外网络尝试仍会使该场景失败。

只有独立 stdio 子进程能调用 Gemini。其输入是稳定的场景编号、用途、调用序号及
生产 `build_request` / `build_answer_request` 生成的请求。
`project_scenario` 移除 gold、accepted values、预期回答、敏感标记等评分标签。
broker 不读 corpus、gold、fixture 或业务状态；它只读取本地会话元数据及自己的账本。
管理员显式确认仍使用独立 confirmation fixture，不把群规则改成模型推断。

broker 使用现有 `GeminiExtractionProvider` / `GeminiAnswerProvider` 的生产验证器、
prompt、schema、token 限制和 20 秒总请求截止时间。
唯一允许目标是
`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent`。
禁止重定向、额外工具、媒体、其他模型或 fallback。每次生产 owner 最多两次尝试，
传输层不另加隐藏重试。broker 明确禁止任何 botocore AWS API 调用。

档案回答仍是“模型选择已有事实索引 → 确定性渲染”，不是另一个自由文本生成产品。
`provider_failure` / `provider_resume` 事件模拟可恢复故障，不发送故障请求或虚构 usage。
这类模拟故障与真实 HTTP 错误在记录中分别可见。

## 真实费用与恢复

生产领域预算依旧在 Moto 中运行，用于验证真实事务和暂停行为；它不是实际费用控制。
真实付费边界只有 `attempts.sqlite3`。

每次可能发送前使用 `BEGIN IMMEDIATE` 预留生产常量 **458752 micro-USD ($0.458752)**。
该上界来自完整模型输入/输出上限，包含额外 thinking 余量，不使用字符数除以四。
预算不足、调用数耗尽、请求形状不受支持或配置漂移都不能发请求。
成功响应和实际 usage 的结算在同一 SQLite 事务中保存；
usage 缺失、非标准价格/媒体、缓存或工具计量不受支持时，不退款。
超过预留上界的异常 usage 保留实际报告值并永久阻止该会话继续申请新尝试。

状态先落 `INFLIGHT` 再调用 HTTP；响应记录为 `RESPONSE`，未知结果为 `UNKNOWN`。
进程崩溃留下的 `INFLIGHT` 同样视为未知。未知尝试保留全部预留，恢复时不重发。
不能保证 Gemini 服务端 exactly-once；生产 owner 的另一次尝试是独立预留的调用，
并不是重发同一个账本身份。

逻辑身份是 `(scenario_id, kind, ordinal)`，记录完整请求哈希及原始请求 JSON。
相同序号的请求变化会拒绝执行，而不是成为新的收费身份。
响应带校验和，读取时验证。无效 schema 的真实响应也保留，下一次尝试有独立序号，
因此缓存不会强迫第二次重试永远返回第一次的无效结果。
缓存命中不发送网络请求、不创建第二笔真实费用，也不生成假 usage。

`session.lock` 拒绝两个编排进程并发使用同一目录；`provider.lock` 保护 broker。
会话锁定模型、价格版本、预算、调用数、速率、完整投影输入、完整 corpus（包括 gold）哈希、确认 fixture 和执行源指纹。
改变这些字段需要新计划，不能在 `--resume` 时提高上限。
独立 gold 标签不会进入模型，broker 只见 corpus 哈希；恢复时不能更改评分依据。
恢复会严格比对初始 `plan.json`，缺失或改动均拒绝，不覆盖旧计划。
出报告前再次检查源指纹；运行中源码变化会停止评分，已提交的场景和费用证据仍保留。

## 文件与验收含义

- `session.json`：冻结的执行配置和源码指纹，不含密钥或 gold。
- `plan.json`：全部计划场景、事件、checkpoint 和问题 ID，先于第一个模型请求保存。
- `attempts.sqlite3`：原始安全请求、原始成功输出、HTTP 状态、usage、延迟、模型返回信息、
  哈希、预留和结算；这是实际传输及费用证据，不是 Moto 账本。
- `scenarios/*.json`：每个场景原子保存实际观测。崩溃前已完成场景可直接复用。
- `progress.json`：已执行/失败场景和费用上界，逐场景更新。
- `observations.jsonl`、`provenance.json`、`report.json`、`report.md`：结束时生成的完整/部分评估产物。

请求、响应和场景文件为本地私有文件（0600，场景目录 0700）。
响应认证头和非成功 HTTP 原始错误正文不保存，避免服务端回显密钥；保留状态和安全错误类别。
成功模型输出若回显密钥则拒绝并脱敏，不写入 payload。
broker stderr 不向用户转发，异常文本和链不写入证据。

`attempts_reserved` 是可能已收费尝试的保守计数；进程在真正联网前崩溃也会留下预留。
不能把它等同于 Google 账单的精确请求数。收费报告使用实际已验证 usage 加未知预留上界。
API free tier 是否实际覆盖不由此工具判断，按标准价上界控制支出。

真实模型错误保留失败/未知记录，不补空事实或未知答案。恢复成功的独立重试可以解除
该请求的未完成标记；仍未完成的场景为 `UNSUPPORTED`，意外领域错误为 `FAILED`，
相应 checkpoint 不伪造，评分继续保留缺失的分母。
已经原子提交的失败场景同样保持原记录，`--resume` 不会悄悄重新采样替换失败结果。

现有 evaluator 的阈值和声明保持不变：真实 HTTP、指标达标、独立标签复核、dev canary、
七天真人群试运行是不同证据。合成时钟下的学习时延不是生产时效证明。

## 本地测试边界

专项测试使用真实 SQLite 事务/锁、真实请求验证器与生产 HTTP provider，
但 HTTP 为 `httpx.MockTransport`，独立进程验证使用本地 stdio 替身。
覆盖预留竞争、发送后崩溃、未知恢复、坏 schema 的独立第二次尝试、费用/次数上限、
配置和请求漂移、缓存不重复计费、固定主机、密钥不落盘、完整计划与领域 factory。
测试通过不代表实际 Gemini 或部署验收已完成。

官方依据：[模型及 token 上限](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite)、
[标准价格](https://ai.google.dev/gemini-api/docs/pricing)、
[项目共享配额](https://ai.google.dev/gemini-api/docs/rate-limits)、
[usageMetadata](https://ai.google.dev/api/generate-content#UsageMetadata)。
