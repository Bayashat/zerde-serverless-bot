# Contributing to Zerde Bot

Thank you for contributing to Zerde Bot. This guide covers development setup from scratch.

---

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Bayashat/zerde-serverless-bot.git
cd zerde-serverless-bot
```

### 2. Install uv

We use [uv](https://github.com/astral-sh/uv) for fast, reliable dependency management.

**macOS / Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify:

```bash
uv --version
```

### 3. Install Python Dependencies

From the project root:

```bash
uv sync --frozen
```

This creates `.venv` and installs all dependencies from the lock file. Activate it when running Python directly in a shell:

```bash
source .venv/bin/activate   # macOS / Linux
# or: .venv\Scripts\activate  on Windows
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values. See the table below for all keys.

**Required:**

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Token from [@BotFather](https://t.me/botfather) |
| `WEBHOOK_SECRET_TOKEN` | Random secret for webhook validation (`openssl rand -hex 32`) |
| `GEMINI_API_KEY` | Google Gemini API key for agent replies, news, summaries, and quiz generation |
| `GEMINI_EMBEDDING_API_KEY` | Optional separate Gemini key for vector embeddings; falls back to `GEMINI_API_KEY` when unset |
| `GROQ_API_KEY` | Groq API key for async spam checks |
| `DEEPSEEK_API_KEY` | Optional DeepSeek fallback key |

**Optional (have defaults):**

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LANG` | `kk` | Default bot language (`kk`, `ru`, `zh`) |
| `TELEGRAM_API_BASE` | `https://api.telegram.org/bot` | Override for local testing proxies |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Bot agent and memory-summary model |
| `NEWS_GEMINI_MODEL` | `gemini-3.1-flash-lite` | News digest model |
| `QUIZ_GEMINI_MODEL` | `gemini-3.1-flash-lite` | Quiz generation model |
| `GROUP_MEMORY_ENABLED` | `true` | Enables recent group memory and long-term memory writes |
| `VECTOR_MEMORY_ENABLED` | `true` | Enables S3 Vectors semantic memory indexing/retrieval |
| `AGENT_ENABLED` | `true` | Enables `/ask`, @mention, reply-to-bot, and proactive agent behavior |
| `AGENT_BOT_USERNAME` | `@zerde_kz_bot` | Bot username used for mention detection |
| `CHATS_KK` / `CHATS_ZH` / `CHATS_RU` | _(empty)_ | Whitelisted bot chats and language mapping |
| `NEWS_CHATS_KK` | _(empty)_ | Comma-separated chat IDs for Kazakh news digest |
| `NEWS_CHATS_ZH` | _(empty)_ | Comma-separated chat IDs for Chinese news digest |
| `NEWS_CHATS_RU` | _(empty)_ | Comma-separated chat IDs for Russian news digest |
| `QUIZ_CHATS_KK` / `QUIZ_CHATS_ZH` / `QUIZ_CHATS_RU` | _(empty)_ | Per-language quiz target chats |

Never commit `.env` — it is in `.gitignore`.

### 5. Install Node.js and AWS CDK CLI (Optional)

Required only if you are working on infrastructure (`infra/`).

1. Install **Node.js (LTS)** from [nodejs.org](https://nodejs.org/) or via `brew install node`.
2. Install the CDK CLI:

```bash
npm install -g aws-cdk
cdk --version
```

All CDK commands in this project are run via `uv run cdk` (e.g. `uv run cdk synth`, `uv run cdk deploy`).

### 6. Pre-commit Hooks

We use [pre-commit](https://pre-commit.com/) for linting, formatting, and type checking.

```bash
uv run pre-commit install
```

Run on all files manually:

```bash
uv run pre-commit run --all-files
```

| Hook / Tool | Purpose |
|-------------|---------|
| Black | Python formatting |
| Isort | Import sorting |
| Flake8 | Linting |
| Trailing whitespace / EOF | Basic hygiene |

### 7. Validate Infrastructure Locally

```bash
uv run cdk synth -c env=dev
```

---

## Project Structure

| Path | Description |
|------|-------------|
| `infra/` | AWS CDK stacks: API Gateway, DynamoDB, SQS, EventBridge, all Lambdas |
| `src/bot/` | Bot Lambda — webhook handler, SQS worker, captcha, voteban, spam, group memory, RAG agent, vector indexing |
| `src/news/` | News Lambda — fetches IT news, summarizes via Gemini, sends multilingual digest |
| `src/quiz/` | Quiz Lambda — generates/sends multilingual developer quizzes |
| `src/shared/python/zerde_common/` | Shared Lambda layer utilities |
| `docs/ARCHITECTURE.md` | Current architecture source of truth |
| `scripts/` | DevOps helpers: OIDC setup, webhook registration |

**Lambda functions and workloads:**

| Lambda | Entry | Trigger | Responsibility |
|--------|-------|---------|----------------|
| `src/bot/` | `main.py` | API Gateway + SQS | Telegram webhook, captcha, voteban, spam checks, `/ask`, agent replies, memory writes, vector indexing |
| `src/news/` | `main.py` | EventBridge (daily) | Fetch news → Gemini/DeepSeek-compatible summary → send multilingual digest |
| `src/quiz/` | `main.py` | EventBridge + bot invoke | Generate quiz questions → send Telegram poll → track scores |

Large changes to architecture, memory, agent behavior, SQS tasks, or infrastructure must update `docs/ARCHITECTURE.md`, `.codex/AGENTS.md`, and `.codex/skills/zerdebot-development/SKILL.md` in the same PR.

---

## Pull Request Process

1. **Fork** the repo and create a branch from `main` following the convention `<type>/<slug>` (e.g. `feat/add-leaderboard-command`).
2. Ensure **pre-commit** passes: `uv run pre-commit run --all-files`.
3. If you changed **infrastructure** (`infra/`), include the output of `uv run cdk diff -c env=dev` in the PR description.
4. Open the pull request — the template will prompt you for What, Why, and Verification steps.

---

## Security

If you find a security issue (e.g. token handling, webhook validation, IAM permissions), do **not** open a public issue. Contact the maintainers privately.

---

## Local Testing and Full Run-through

For setting up an AWS account, creating a Telegram bot, configuring tokens, and deploying end-to-end, see **[Local Testing Guide](docs/LOCAL_TESTING.md)**.
