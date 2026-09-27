# Zerde Bot

Zerde is a Python Telegram community bot running on AWS Lambda, SQS and DynamoDB. It provides explicit AI answers and media analysis, moderation, captcha, voteban, news digests and quizzes.

Memory V2 is under validation. It records explicit self-statements with group-scoped Telegram identities, evidence and lifecycle controls. Automatic group participation, reactions, channel comments, historical imports and experimental contests are retired. Production memory is not enabled merely by deploying the code.

See [current architecture](docs/ARCHITECTURE.md), [implementation status](docs/goals/zerdebot-memory-v2/TASKS.md) and [validation evidence](docs/MEMORY_PUBLIC_EVALUATION.md). Older audit and evaluation reports describe their frozen versions; they are not current deployment instructions.

## Explicit answers and memory

- `/ask`, direct mentions and requested replies to the bot remain available without long-term memory. When context is unavailable, the bot must say so rather than infer that no data exists.
- Personal facts come only from the person's explicit self-statements in the same group. Facts have evidence, versions and correction/forget support; profiles are views of valid facts.
- V2 stores raw messages for 30 days. Extraction and reliable recovery use the independent V2 table and queue. V1 semantic retrieval and rule-based personal-fact fallback are removed.
- `/memory` exposes the current controls and usage. A refusal to change another person's information is distinct from a temporary database failure or disabled learning.
- Explicit requests may analyze supported media and related album items. Temporary media metadata is owned by V2; media analysis is not automatically added to personal facts. There is no background analysis of ordinary media.

The sole memory/control/source/lifecycle owner is `src/bot/services/memory_v2`. The explicit answer orchestration stays in `group_agent.py`; its name does not imply autonomous group behavior.

## Runtime and storage

| Entry | Responsibility |
|---|---|
| `src/bot/main.py` | Telegram webhook, main SQS tasks, explicit answers and current business handling |
| `src/bot/memory_worker_main.py` | V2 extraction, recovery and lifecycle work |
| `src/news/main.py` | News collection and per-group delivery recovery |
| `src/quiz/main.py` | Poll publication, scoring and recovery |
| `src/operations/main.py` | Fault, recovery and budget notifications to the configured administrator |
| `src/shared/python/zerde_common` | Shared configuration, providers, error handling and redacted logging |

Each environment retains three tables: business stats, Quiz and Memory V2. The main business queue, V2 queue and operational failure queues have separate responsibilities. Old message types are rejected early on the mixed main queue so delayed deliveries cannot revive removed behavior.

S4 removes the legacy table/vector infrastructure declarations and dedicated indexer entry. Removing declarations is not proof that cloud objects have disappeared: production `Retain` resources require separate physical deletion. The [retirement inventory](docs/goals/zerdebot-memory-v2/RETIREMENT_INVENTORY.md) records what is deleted, kept or still under investigation. Backup/PITR obligations remain separate.

## Development and deployment

```bash
uv sync --frozen --python 3.13.6
uv run --frozen --python 3.13.6 pytest tests/ -q
uv run --frozen --python 3.13.6 pre-commit run --all-files
```

Use `.env.example` for supported configuration. Secrets are read from the environment-specific SSM prefix in deployed functions. `DEV_RUNTIME_ENABLED=false` keeps dev idle by default; changing it does not enable group learning. The original project metering epoch must not be reset.

```bash
cd infra
uv run cdk synth -c env=dev
uv run cdk diff -c env=dev
```

Build checks must inspect all five real ARM Lambda packages and their shared layer with `scripts/verify_lambda_bundles.py`. Test success, a PR merge, deployed-package verification and product acceptance are recorded separately. Follow the [execution and cleanup contract](docs/goals/zerdebot-memory-v2/FINISH_EXECUTION.md) before changing deployed resources or enabling a group.

The Memory V2 cost inventory continues to meter the original Bot/Worker, V2 table/queue and incremental alarm scope. Retiring vectors does not reset charges, unresolved provider results or budget history. Estimated application cost is not the project's final bill.
