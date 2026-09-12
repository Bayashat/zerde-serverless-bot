# Memory V2 runtime integration

Status: **IMPLEMENTED_UNPROVEN**. This connects the independently reviewed Z01,
Z04–Z07, Z13 and Z17 changes. It does not activate a chat, delete old data, or
establish model quality or real Telegram acceptance.

## Admission and ownership

`services.memory_v2.runtime` is the single lazy composition module shared by the
webhook and dedicated worker. Missing V2 table or queue configuration cannot fall
back to the legacy table or mixed business queue. Configured storage still requires
an explicit ACTIVE V2 control record; no deployment seed creates one.

The authenticated, whitelisted webhook converts only the original message text or
caption. Replied text, attachment contents and model-produced media analysis are
never canonical sources. Telegram UTF-16 blockquote offsets are converted to Python
character spans. Invalid quote ranges conservatively mark the whole body quoted.

Every eligible personal message first advances source observation metadata, before
captcha and spam decisions. Empty, unsafe or command edits can therefore invalidate
an existing fact without becoming learning input. Deterministically obsolete or
same-time ambiguous edits are acknowledged without learning; a transaction conflict
or database failure returns HTTP 500 for redelivery.

Captcha-pending, enforced and queued messages cannot use the safe admission lane.
For queued moderation, the original body is staged in V2 with the exact moderation
input fingerprint. The SPAM_CHECK task receives only a source reference in addition
to its existing classification payload. A persisted CLEAN receipt authorizes promotion
through a cross-table transaction. The original staged body, never the task's text
or replied context, becomes RAW/HEAD/WORK. A failed enqueue remains recoverable from
WORK. A pending or unavailable review never silently becomes clean.

Immediate CLEAN processing asks the same ingestion owner to promote, reducing normal
learning latency. A five-minute recovery invocation covers failed deliveries and
manual-review completions. Paused admissions remain pending; actual expiry is
reported separately. See [ingestion states](memory-v2-ingestion.md).

## Infrastructure and costs

- One independent `zerde-serverless-memory-v2-queue-{env}` and DLQ; the main bot may
  send to it but cannot consume it. The worker cannot consume the mixed business queue.
- Worker: Python 3.13 ARM64, 512 MB, 120-second timeout, maximum concurrency two.
  SQS batches up to 20 references with a 20-second window; visibility is 740 seconds
  (six invocation timeouts plus the batching window), partial batch failures enabled.
- Recovery: EventBridge every five minutes, exact schema-2 recovery event, bounded
  four-page runs with durable progress maintained by the domain recovery owner.
- Dev defaults idle: worker reservation zero, mapping and recovery disabled, no dev
  alarms. An ACTIVE control record alone does not start an idle dev runtime.
- Worker IAM reads only the Gemini SSM secret, accesses its own V2 table, and uses
  scoped moderation/quota keys in the stats table. Receipt recovery uses a metadata
  projection on Scan; DynamoDB Scan does not support a LeadingKeys condition.
- Dev and prod model calls share the **prod V2 cost ledger**. Dev permission on that
  table is restricted to `MEMORY_BUDGET#*` and `MEMORY_ATTEMPT#*`; it cannot query or
  scan prod profiles. A missing/unavailable shared ledger stops optional calls.
- Active runtime adds five actionable worker/queue alarms, bringing this integration
  to 22 alarms. Both alarm and recovery notifications use Z17's private operations
  transport. Model budget semantics are in [the cost contract](MEMORY_V2_BUDGET.md).
  Project tags still require account activation; this is not an AWS billing hard cap.

The worker's SQS-processing DLQ and asynchronous recovery delivery failures use the
same dedicated DLQ. Their envelopes differ: SQS task bodies are schema-2 references;
EventBridge/Lambda failure envelopes must be inspected as metadata and routed back
to the recovery entrypoint. Do not feed an arbitrary failed event into fact writes,
purge a mixed queue, or replay an expired epoch.

## Build and acceptance

`httpx`, `httpcore` and `dnspython` are explicit locked bot/news dependencies. The
shared asynchronous transport resolves DNS without a blocking resolver thread,
preserves the original HTTP host and TLS name, and permits cancellation of DNS,
connection and response reads. Outer request deadlines still do not promise an
absolute deadline for unrelated synchronous AWS SDK or CPU work.

CDK layer annotations use `ILayerVersion`, verified under Python 3.13 rather than
relying on Python 3.14's deferred annotation evaluation. The strict asset probe registers the
sixth handler, `memory_worker_main.lambda_handler`; a newly added unregistered handler
fails verification. Template tests use stub code and are not packaging proof.

Run the complete tests, actual CDK synth and
`scripts/verify_lambda_bundles.py` against that fresh assembly. The latter imports
all six real packages in the pinned Python 3.13 ARM64 Lambda image with networking
disabled. Test moderation/source/fact transactions against the real boto3 Resource
serialization and Moto, including a classification payload containing someone else's
quoted text, to prove the admitted body remains the author's original message.

Before activation, run Z10 cleanup rehearsal and pass Z11's synthetic and real-world gates.
Z08/Z09 public integration is described below. Read back actual
Lambda timeouts, queue settings, IAM, alarm actions and current control state after
any separately authorized deployment. A queue message or successful Lambda invocation
alone does not prove a correct profile. Failure recovery remains explicit question
answering without long-term memory; legacy learning must stay retired.

## Z08/Z09 public answering and control integration

The source now wires `/ask`, explicit mentions and clear bot replies through
`MemoryPublicAnswers`, with live Telegram membership and current identity hints.
The selector returns only existing fact indices, `unknown` or `general`. Even an
empty profile goes through this distinction when optional model budget is available;
a deterministic `/memory about` display makes no model call. Every personal claim
is rendered from a current fact with its minimal evidence, UTC date and Telegram
source link. City/occupation/current-project facts older than 180 days are labeled
as last mentioned. Current aliases are verified with `getChatMember`; a display
name or a similar fact cannot merge people. Basic groups without a supported
`t.me/c` link explicitly show unavailable links rather than inventing one.

The answer parser accepts one final text part with optional opaque string
`thoughtSignature` and an absent or exactly false boolean `thought`. These are
documented Gemini Part metadata; the signature is neither decoded nor returned
as answer/context. The existing provider limit bounds the complete HTTP response
at 100 KB. Thinking content, tool/function/media/code parts, unknown extra keys,
additional parts and invalid selection JSON still fail closed.
[Gemini Part reference](https://ai.google.dev/api/generate-content?hl=en#Part)
The 2026-09-11 real smoke exposed the prior exact-text-key check rejecting valid
signed selections and causing an unnecessary paid retry. That run and its costs
remain historical failure evidence; offline parsing of its stored responses is
diagnostic only, not evidence of sent answers or a corrected quality benchmark.

The only public send identity is `tg:<chat_id>:<message_id>` for both memory and
plain/media answers. A released/expired lease can be reclaimed only when no
`ANSWER_REQUEST` exists, proved in the same transaction. A prepared, partial,
SENDING, SENT or UNKNOWN request blocks blind resending, including switching from
plain to memory after a budget recovery. A never-activated/STOPPED group still has
body-free plain-answer deduplication; creating these receipts does not enable
learning. Safe Telegram read failures request webhook/SQS retry, while uncertain
send results retain their durable unknown state. This is not exactly-once delivery:
an HTTP success followed by failed receipt persistence or a crash immediately
before HTTP may require inspection rather than an automatic second send.

All questions carry an original-date/source-version/epoch/actor-generation fence.
A saved original request cannot bypass a newer edit, deletion, forget cutoff or
new epoch. Actor and referenced-source leases last 360 seconds, longer than the
300-second Bot invocation. Sending checks more than 40 seconds remain and uses one
cancellable 20-second HTTP attempt. Deletion hides facts immediately but confirms
completion only after registered sends drain. Unobserved Telegram deletions cannot
be discovered automatically; edits delivered by Telegram and `/memory forget this`
enter the canonical source invalidation owner.

`/memory about me|group [page]`, `correct <fact@version> <value>`,
`wrong <fact@version>`, `group confirm rule|decision <value>`, `forget me|this|group`,
`optout`, `optin`, `status`, and administrator-only `on|off` share one control
adapter. Group corrections/forget and confirmations require a current group admin;
a configured bot owner is not a group-admin bypass. Personal corrections require
that person's source. `forget me` permits later fresh messages; `optout` also stops
future learning. Old commands have a seven-day body-free control receipt and a
one-day acceptance window, with an original identity and generation fence. The
same command cannot erase newly rebuilt data after a retry. Control tombstones
are retained for anti-replay and are not erased facts or transcripts.

`ExplicitContextRepository` preserves inherited business settings storage
but never writes or reads old `AGENT_REPLY` bodies. Album membership goes only to
V2 metadata with a one-day original-time lifetime; no captions, filenames, aliases
or media analysis become long-term facts. At most four items are reloaded from
current sources before a queued media answer; leases bind their exact versions.
The explicit-task protocol is `explicit-v2-sources-2026-09`; prior tasks are retired.

## Group sample and optional work

Group rules/decisions are current administrator-confirmed facts. `/memory about
group` shows eight facts per page plus a sample of up to ten validated sources in
the seven-day topic window. This is a labeled technical-topic **sample**, not full
group statistics, personality or relationship analysis. The output includes source
links, window, sample size and last inventory traversal. See [topic semantics](MEMORY_V2_TRENDS.md).
A periodic group rotation prevents one group permanently owning the maintenance
window. The five-minute worker recovery allocates at most 20 seconds to purges,
60 to ingestion and 15 to trend maintenance; ordinary batches use at most ten
seconds for contributions and 90 for extraction. Failed pages remain recoverable.
AWS budget preflight pauses optional classification without changing model-budget
semantics; deterministic profile/control operations remain available.

## Shared cost instrumentation and first deployment

[Shared SDK metering](MEMORY_V2_COST_METER.md) now installs actual DynamoDB/SQS
factory hooks. The outer Bot/worker `finally` closes each invocation exactly once;
Bot only starts a span when a V2 operation is first touched. The model ledger
covers full answer/extraction attempts, including retries and uncertain billing.
[Cost monitoring](MEMORY_V2_COST_MONITOR.md) runs hourly in the **existing prod Bot**,
not a seventh Lambda. It reads exact resources, computes conservative gross usage,
publishes durable threshold events to the existing private operations notifier,
and requires complete/fresh inventory coverage before optional model reservations.
Dev and prod share this ledger but never share personal facts. Both environments'
maximum ten memory alarms are reserved at USD 1/month even while dev is idle.

`MEMORY_COST_METERING_STARTED_AT` has one source across `.env.example`, preview and
deploy workflows, and CDK. Default `0` means no first deployment has been scheduled:
the monitor rule is disabled and optional V2 work cannot obtain a permit. Before
**the first dedicated V2 infrastructure deployment**, set the same approved fixed
UTC timestamp in dev/prod configuration. Do this while learning remains STOPPED;
do not wait until a later learning activation or move the time forward to discard
history. Deploying a table days earlier with zero and using the later activation
time would correctly fail creation-time reconciliation. Compact inventory is
resolved by CloudFormation and hashed at runtime; its declaration fits Lambda's
4 KiB environment limit. Missing dev resources or instrumentation keep the project
UNVERIFIED. The monitor's own invocation is metered, and monitored reads cannot be
blocked by their own optional-work budget guard.

All local model/Telegram/CloudWatch responses in tests are synthetic. Real Logs
Insights parsing, AWS configuration readback, model quality, exact Telegram source
links and the seven-day single-group trial remain separate release gates. Source
integration and successful packaging do not mark Z11 or the production wipe done.

### 暂停范围

模型门槛暂停个人事实抽取和记忆增强问答；AWS 估算门槛还暂停可选话题维护。为履行短期留存、故障恢复及未处理覆盖率契约，来源观察、30 天消息保存、待处理任务、安全审核恢复与更正/删除控制继续运行并可能产生 AWS 费用；暂停期间不会生成新的模型事实。恢复后只能处理仍有效且未逻辑到期的来源，过期必须计入覆盖率。此策略不声称停掉全部 memory AWS 消耗，也不提供 AWS 账单硬上限。若未来要停止新原文摄取，应作为单独数据覆盖率/恢复契约变更评审。

显式 plain/media 的来源验证回调贯穿 Gemini 每次重试与每家 fallback 的真实 HTTP 入口；第一次失败后编辑或遗忘不会让旧内容进入下一次供应商调用。校验的数据库错误传播为可重试状态，不会误解释成供应商失败再继续换模型。最终 Telegram 发送仍独立复验。

更正命令里的合法 `fact@version` 是控制引用，不是个人事实正文；同一 source_event 将精确匹配的第三个 token 用等长空白投影后用于 OBS hash 和 confirmation RAW，保留新值与引用证据位置。无效引用或新值中的敏感内容继续被拒绝，未放宽敏感过滤。
