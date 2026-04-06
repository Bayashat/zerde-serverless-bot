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
| `TELEGRAM_BOT_TOKEN` | Token from [@BotFather](https://t.me/botfather) |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | Random secret for webhook validation (`openssl rand -hex 32`) |
| `GEMINI_API_KEY` | Google Gemini API key (for news summarization and quiz translation) |
| `QUIZAPI_KEY` | [QuizAPI](https://quizapi.io/) key (for daily quiz questions) |

**Optional (have defaults):**

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LANG` | `kk` | Default bot language (`kk`, `ru`, `zh`) |
| `TELEGRAM_API_BASE` | `https://api.telegram.org/bot` | Override for local testing proxies |
| `AI_PROVIDER` | `gemini` | AI provider for news/quiz (`gemini`) |
| `LLM_MODEL` | `gemini-2.5-flash` | LLM model name |
| `NEWS_CHATS_KK` | _(empty)_ | Comma-separated chat IDs for Kazakh news digest |
| `NEWS_CHATS_ZH` | _(empty)_ | Comma-separated chat IDs for Chinese news digest |
| `NEWS_CHATS_RU` | _(empty)_ | Comma-separated chat IDs for Russian news digest |
| `QUIZ_CHATS` | _(empty)_ | Comma-separated chat IDs for daily quiz |

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
| `src/bot/` | Bot Lambda — webhook handler, captcha, voteban, quiz scoring, stats |
| `src/news/` | News Lambda — fetches IT news, summarizes via Gemini, sends multilingual digest |
| `src/quiz/` | Quiz Lambda — fetches tech questions from QuizAPI, sends daily Telegram quizzes |
| `scripts/` | DevOps helpers: OIDC setup, webhook registration |

**Three independent Lambda functions:**

| Lambda | Entry | Trigger | Responsibility |
|--------|-------|---------|----------------|
| `src/bot/` | `main.py` | API Gateway + SQS | Captcha, voteban, quiz score tracking, `/stats`, `/quizstats` |
| `src/news/` | `main.py` | EventBridge (daily) | Fetch news → Gemini summary → send to Kazakh/Russian/Chinese chats |
| `src/quiz/` | `main.py` | EventBridge (daily) | Fetch quiz questions from QuizAPI → send Telegram poll → track scores |

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
