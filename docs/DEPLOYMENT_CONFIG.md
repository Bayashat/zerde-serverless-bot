# Deployment configuration and dependency locks (Z04)

`pyproject.toml` and the root `uv.lock` own dependency resolution. The three
Lambda `requirements.txt` files and `infra/requirements.txt` are generated pip
inputs for CDK. They contain exact versions, transitive dependencies and hashes;
never edit them independently. The vector indexer uses the bot package.

| Group | Shipped dependencies |
| --- | --- |
| `lambda-common` | boto3, its matching botocore, urllib3 and their dependencies |
| `lambda-bot` | common + Pillow |
| `lambda-news` | common + feedparser + google-genai |
| `lambda-quiz` | common + google-genai |
| `dev` | All Lambda groups plus development tools; never exported into Lambda packages |

GitHub workflows pin uv `0.11.3` and check exports before synthesis or deployment:

```bash
uv lock
uv run python scripts/export_requirements.py
uv run python scripts/export_requirements.py --check
```

This is the supported bridge to CDK's entry-local requirements discovery, as
described by [AWS packaging documentation](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_lambda_python_alpha/README.html)
and [uv export documentation](https://docs.astral.sh/uv/concepts/projects/export/).
The lock guarantees dependency selection and file hashes, not bit-for-bit identity
of the mutable CDK builder toolchain or Python bytecode timestamps.

## Configuration contract

The following 21 previously omitted repository variables are now mapped in both
`deploy.yml` and `pr_check.yml`. The example, runtime and synthesized environments
are checked together in `tests/test_infra_configuration.py`.

| Variable | Type | Default |
| --- | --- | --- |
| MAIN_TASK_QUEUE_RETENTION_DAYS | integer, 1–14 days | 1 |
| MAIN_TASK_DLQ_RETENTION_DAYS | integer, 1–14 days | 14 |
| VECTOR_MEMORY_QUEUE_RETENTION_DAYS | integer, 1–14 days | 4 |
| VECTOR_MEMORY_DLQ_RETENTION_DAYS | integer, 1–14 days | 14 |
| GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS | integer days | 30 |
| GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS | integer days | 7 |
| GROUP_MEMORY_LONG_TERM_RETENTION_DAYS | integer days | 3650 |
| GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS | integer days | 3650 |
| GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS | integer days | 3 |
| GROUP_MEMORY_EXTRACTOR_PROVIDER | string | gemini |
| GROUP_MEMORY_EXTRACTOR_MODE | string | gemini_candidate_only |
| GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE | float | 0.65 |
| GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT | integer | 50 |
| GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT | integer | 20 |
| AGENT_BOT_ID | optional integer | empty |
| AGENT_PROACTIVE_DELAY_SECONDS | integer seconds | 45 |
| MULTIMODAL_ENABLED | boolean | true |
| MULTIMODAL_MAX_DOWNLOAD_BYTES | integer bytes | 12000000 |
| MULTIMODAL_INLINE_MAX_BYTES | integer bytes | 8000000 |
| MULTIMODAL_TEXT_FILE_MAX_CHARS | integer characters | 20000 |
| VECTOR_MEMORY_SCHEMA_VERSION | string | 1 |

Raw messages and album metadata default to **30 days independently of the legacy
retention variable**, even if `GROUP_MEMORY_RETENTION_DAYS=3650`. Explicit raw
overrides remain supported. Changing environment variables affects future writes;
it does not shorten TTLs already stored in DynamoDB, delete old rows, or reopen
memory learning. Legacy long-term/summary defaults remain for compatibility until
the separately approved legacy cutover; Memory V2 has its own lifecycle.

Ten preview defaults now match deployment: captcha timeout `120`, kick duration
`31`, voteban/forgive thresholds `7`/`7`, Gemini RPD `500`, quiz RPD `20`, and the
existing bot/news/quiz Gemini plus DeepSeek model values. Model names are unchanged.
Other non-model drift is aligned: recent memory `300`, agent context `100`, vector
index throttle `3` seconds, proactive limit `3`. Unused `AI_PROVIDER`,
`WTF_GEMINI_MODEL` and `FALLBACK_MODEL` workflow entries are removed.

## Security dependency refresh

On 2026-09-10 the repository's GitHub Dependabot API reported 24 open alerts in
`uv.lock`. Case-insensitive package names identify six affected packages. Z04
updates to the reported fixed floors, with only required CDK transitive changes:

| Package | Locked version | Impact / representative advisory |
| --- | --- | --- |
| Pillow | 12.3.0 | Bot/indexer native image processing; [GHSA-jjj6-mw9f-p565](https://github.com/advisories/GHSA-jjj6-mw9f-p565) |
| urllib3 | 2.7.0 | All runtime HTTP/SDK packages; [GHSA-qccp-gfcp-xxvc](https://github.com/advisories/GHSA-qccp-gfcp-xxvc) |
| idna | 3.15 | News/quiz HTTP dependencies; [GHSA-65pc-fj4g-8rjx](https://github.com/advisories/GHSA-65pc-fj4g-8rjx) |
| pyasn1 | 0.6.4 | News/quiz Google authentication dependencies; [GHSA-m4p7-r5rc-7g4j](https://github.com/advisories/GHSA-m4p7-r5rc-7g4j) |
| cryptography | 50.0.0 | News/quiz native cryptography; [GHSA-g6cj-pr64-35w5](https://github.com/advisories/GHSA-g6cj-pr64-35w5) |
| aws-cdk-lib | 2.253.0 | Infrastructure/build only; [GHSA-464c-974j-9xm6](https://github.com/advisories/GHSA-464c-974j-9xm6) |

The Python Lambda alpha construct is paired at `2.253.0a0`; JSII and assembly
schema update only as required by that pair. boto3/botocore remain matched at
`1.42.38`. Fixing a local branch does not mean GitHub has closed the main-branch
alerts or that deployed Lambda code has been updated.

## Build and release evidence

```bash
cd infra
uv run --frozen cdk synth -c env=dev --quiet
cd ..
uv run --frozen python scripts/verify_lambda_bundles.py
cd infra
uv run --frozen cdk diff -c env=dev --no-change-set
```

The bundle verifier uses the actual asset paths and shared layer from the CDK
template. It imports all five registered handlers (including operations) inside the pinned AWS Python 3.13 ARM64
runtime image with networking disabled and only synthetic identifiers. It checks
that boto3/botocore/urllib3 and native modules load from `/var/task`, verifies
installed package versions against exports, creates a Pillow PNG and exercises
cryptography. The infrastructure unit tests intentionally stub bundling and are
not substitutes for this check. Both deployment and infrastructure-preview CI run
the real bundle probe; deployment runs it before changing AWS resources.

The runtime probe image is pinned by digest in `scripts/verify_lambda_bundles.py`.
Update that digest deliberately when validating a newer Lambda runtime. The
Docker builder may report its own Poetry/urllib3 dependency conflict; Poetry is
not exported into Lambda assets. Judge runtime compatibility from the isolated
runtime probe, not the builder's preinstalled tools.

Deployment is a separate gate: inspect the intended environment's CDK diff and
verify live raw retention is `30` after rollout. Preserve the Z01 legacy guard and
the Z12/Z13 rollout prerequisites when integrating branches. No AWS deployment,
repository-variable mutation, old-row TTL rewrite, or production acceptance is
performed by these local checks.

Local Z04 evidence (2026-09-10): all 599 repository tests pass, including 23
configuration/packaging checks; pre-commit passes for tracked and newly added
files. Real CDK synthesis with the patched lock succeeds. All four handler probes
pass on `aarch64`, Python `3.13.15`, with boto3 `1.42.38` and urllib3 `2.7.0` loaded
from the assets. The read-only dev diff reports the four Lambda artifacts and
shared layer changing, including raw retention `3650 -> 30` on bot/indexer.
That local diff uses defaults, so it also reflects absent local chat/configuration
variables. It is evidence of synthesis and drift detection, not an approved
deployment manifest; recreate the release diff with the intended environment's
variables before deployment.

运维入口、dev 按需开关、成本标签激活及 Quiz 恢复步骤见 [docs/OPERATIONS.md](OPERATIONS.md)。Z17 增加独立 operations Lambda（仅 lambda-common）；V2 worker 接入时更新严格 bundle handler 注册。


## Lambda environment capacity after legacy retirement

On 2026-09-11 the production update failed because AWS measured the Bot environment
as **4114 bytes**, above its 4096-byte limit. The earlier 3573-byte check summed only
key/value text. It missed JSON separators, quotes and escaping inside values such
as `CHAT_LANG_MAP` and `MEMORY_COST_INVENTORY`. For that exact resolved environment,
compact JSON reproduces 4114 bytes; JSON with whitespace and a `Variables` wrapper
measures 4298 bytes. Do not treat unresolved CloudFormation token lengths or a
key/value-only sum as deployment acceptance.

`infra/components/bot.py` now omits only exact values equal to the runtime defaults
for 19 retired proactive, ambient-reaction and legacy-extractor tuning keys. The
remaining Python compatibility modules still define those same defaults in
`src/bot/core/config.py`. Non-default deploy inputs remain present, and all feature
switches, bot identity, explicit-question models/context, raw retention, chat lists,
secret references and queue/table identifiers remain unchanged. Vector indexer
inherits the compact Bot environment; the V2 worker keeps its existing allowlist.
Existing `.env.example` and workflow inputs remain valid; an omitted default is
not a removed configuration option and an override is never silently discarded.

The production candidate omits 15 equal defaults; four non-default retired tuning
values remain. Its Bot compact JSON becomes **3297 bytes**, or **3451 bytes** with
the conservative wrapper, leaving at least **645 bytes** under 4096. Vector indexer
becomes 2657/2793 bytes respectively. These figures identify that release's
configuration, not a universal promise for larger future chat lists or overrides.
No Lambda ZIP, model prompt, secret, data, schedule or business behavior changes in
this capacity correction. The separately reviewed old summary-rule removal has
its own infrastructure delta.

| Retired settings with equal defaults omitted | Production defaults used |
| --- | --- |
| `AGENT_PROACTIVE_DELAY_SECONDS`, `AGENT_PROACTIVE_FINAL_THRESHOLD` | `45`, `0.72` |
| `AGENT_PROACTIVE_DECISION_GROQ_MODELS` | Existing runtime model-pool default, byte-for-byte unchanged |
| `AGENT_PROACTIVE_DECISION_CONTEXT_CHARS`, `AGENT_PROACTIVE_DECISION_ALLOW_DEEPSEEK_FALLBACK` | `4000`, `false` |
| `AMBIENT_REACTIONS_CONFIDENCE_THRESHOLD`, `AMBIENT_REACTIONS_DECISION_CONTEXT_CHARS` | `0.80`, `3000` |
| `AMBIENT_REACTIONS_DECISION_GROQ_MODELS` | Existing runtime model-pool default, byte-for-byte unchanged |
| `AMBIENT_REACTIONS_MIN_GAP_PER_CHAT_SECONDS`, `AMBIENT_REACTIONS_MAX_PER_CHAT_PER_DAY` | `60`, `100` |
| `GROUP_MEMORY_EXTRACTOR_PROVIDER`, `GROUP_MEMORY_EXTRACTOR_MODE` | `gemini`, `gemini_candidate_only` |
| `GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE`, `GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT`, `GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT` | `0.65`, `50`, `20` |

The production call boundary is `main.py` → webhook or `sqs_task_router.py`.
`memory_cutover.RETIRED_TASK_TYPES` discards legacy learning/social tasks before
processing. `group_agent.handle_update` routes requested replies, while the V2
extractor has its own contract; neither reactivates these retired branches. The
unchanged default values also protect import-time compatibility of old modules.

Tests verify all 19 omissions against the actual runtime defaults, preserve every
non-default override, resolve account/region/resource references and nested JSON
for realistic dev/prod environments, and require the conservative serialized Bot
environment to remain below 3500 bytes. Before release, resolve the real target
values again and retain the computed size plus actual AWS update/configuration
readback. No user IDs or credentials belong in repository capacity fixtures.
