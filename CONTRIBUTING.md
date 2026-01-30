# Contributing to Zerde Bot

First off, thanks for taking the time to contribute! 🎉

The following is a set of guidelines for contributing to Zerde Bot.

---

## 🛠️ Development Setup

### 1. Environment Setup

We use `uv` for ultra-fast package management.

```bash
# Install dependencies
uv sync --frozen

# Activate virtual environment
source .venv/bin/activate
```

### 2. Pre-commit Hooks

We use [pre-commit](https://pre-commit.com/) to ensure high code quality (Linting, Formatting, Type Checking) before every commit.

```bash
# Install hooks
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files
```

**What is checked?**

* **Black:** Formats Python code.
* **Isort:** Sorts imports.
* **Flake8:** Lints Python code.
* **Trailing Whitespace / End of File Fixer.**

### 3. Local Testing

Currently, unit tests are under development.

You can run the CDK synthesis locally to ensure your infrastructure code is valid:

```bash
uv run cdk synth -c env=dev
```

---

## 📂 Project Structure

| Path | Description |
|------|-------------|
| `infra/` | AWS CDK Stacks. Defines API Gateway, DynamoDB, SQS, and Lambdas. |
| `src/receiver/` | Receiver Lambda. Entry point. Validates Webhook secret and pushes to SQS. |
| `src/worker/` | Worker Lambda. Processes logic (Captcha, Stats) and calls Telegram API. |
| `src/worker/repositories/` | Data Access Layer. Shared code for DynamoDB and SQS interactions. |
| `src/worker/services/` | Business Logic Layer. Shared code for message formatting and handler logic. |
| `scripts/` | DevOps Tools. Scripts for OIDC setup and Webhook management. |

---

## 📦 Pull Request Process

1. **Fork** the repository and create your branch from `main`.
2. Make sure your code passes **pre-commit** checks.
3. If you've changed infrastructure (`infra/`), please include the output of `cdk diff` in your PR description (our CI will also auto-comment this).
4. Issue that pull request!

---

## 🔐 Security

If you discover a potential security vulnerability (e.g., in the token handling logic), please **do not** open a public issue. Contact the maintainer directly.
