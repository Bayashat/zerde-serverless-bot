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

**Or via pip (if you prefer):**

```bash
pip install uv
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

This creates a virtual environment (e.g. `.venv`) and installs all dependencies from the lock file. Activate it when you need to run Python in a shell:

```bash
source .venv/bin/activate   # macOS / Linux
# or: .venv\Scripts\activate  on Windows
```

### 4. Install Node.js and AWS CDK CLI (Optional)

The project uses **AWS CDK** for infrastructure. The CDK app is written in Python, but the **CDK CLI** is a Node.js tool and must be installed separately.

1. **Install Node.js (LTS)**
   Use [nodejs.org](https://nodejs.org/) or your system package manager (e.g. `brew install node` on macOS).

2. **Install the AWS CDK CLI globally:**

```bash
npm install -g aws-cdk
```

Verify:

```bash
cdk --version
```

All CDK commands in this project are run via `uv run cdk` so that they use the project’s Python environment and app code (e.g. `uv run cdk synth`, `uv run cdk deploy`).

### 5. Pre-commit Hooks

We use [pre-commit](https://pre-commit.com/) for linting, formatting, and type checking before each commit.

```bash
uv run pre-commit install
```

Run on all files (optional):

```bash
uv run pre-commit run --all-files
```

**What runs:**

| Hook / Tool | Purpose |
|-------------|---------|
| Black       | Python formatting |
| Isort       | Import sorting |
| Flake8      | Linting |
| Trailing whitespace / EOF | Basic hygiene |

### 6. Validate Infrastructure Locally

To check that the CDK app and stacks are valid (no need to deploy):

```bash
uv run cdk synth -c env=dev
```

---

## Project Structure

| Path | Description |
|------|-------------|
| `infra/` | AWS CDK stacks (API Gateway, DynamoDB, SQS, Lambdas). |
| `src/receiver/` | Receiver Lambda: webhook entry, validates secret, enqueues to SQS. |
| `src/worker/` | Worker Lambda: business logic (captcha, stats), calls Telegram API. |
| `src/worker/repositories/` | Data access (DynamoDB, SQS, Telegram client). |
| `src/worker/services/` | Business logic and message handling. |
| `scripts/` | DevOps: OIDC setup, webhook registration. |

---

## Pull Request Process

1. **Fork** the repo and create a branch from `main`.
2. Ensure **pre-commit** passes (run `uv run pre-commit run --all-files` if needed).
3. If you changed **infrastructure** (`infra/`), include the output of `cdk diff -c env=dev` in the PR description (CI may also comment it).
4. Open the pull request.

Branch and commit format should follow the project’s Git conventions (see repository rules or root docs).

---

## Security

If you find a security issue (e.g. token handling, webhook validation), do **not** open a public issue. Contact the maintainers privately.

---

## Local Testing and Full Run-through

For setting up an AWS account, creating a Telegram bot, configuring the token, and running a full local/deploy test, see **[Local Testing](docs/LOCAL_TESTING.md)**.
