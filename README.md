# 🛡️ Zerde Bot

![Python](https://img.shields.io/badge/Python-3.13-blue.svg)
![AWS CDK](https://img.shields.io/badge/AWS-CDK-orange.svg)
![Architecture](https://img.shields.io/badge/Architecture-Serverless-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Zerde** is a production-ready, serverless Telegram bot designed for IT community management.

Built with **Python** and **AWS CDK**, it leverages an event-driven architecture to handle high concurrency, enforce captcha verification, and track community statistics—all without managing a single server.

---

## ✨ Features

* **🛡️ Smart Verification (Captcha):** Interactive "I am human" verification with a strict **60-second auto-kick** mechanism (powered by SQS Delay Queues).
* **📊 Community Analytics:** Tracks joins, verification rates, and calculates group activity levels.
* **⚡ High Concurrency:** Buffers traffic via Amazon SQS to prevent data loss during spikes (e.g., raiding).
* **☁️ Infrastructure as Code:** Fully reproducible deployments using AWS CDK.

---

## 🚀 Deployment Guide

### Prerequisites

* **Python 3.13+** & **[uv](https://github.com/astral-sh/uv)** (Package Manager)
* **Node.js & NPM** (For AWS CDK CLI)
* **AWS CLI** configured (`aws configure`)
* A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 1. Installation

```bash
git clone https://github.com/Bayashat/zerde-serverless-bot.git
cd zerde-serverless-bot

# Install dependencies (Production + Dev)
uv sync --frozen
```

### 2. Configuration (Crucial Step)

You need to generate a secure secret for webhook validation before deploying.

Copy the example environment file:

```bash
cp .env.example .env
```

Generate a random secret and fill your `.env`:

```bash
# Generate a random 32-byte hex string
openssl rand -hex 32
```

Edit `.env` and fill in the values:

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_WEBHOOK_SECRET_TOKEN=<PASTE_YOUR_GENERATED_SECRET_HERE>
```

### 3. Deploy Infrastructure

Deploy the stack to your AWS account. This will create the Lambda functions and set the environment variables using the `.env` file you just created.

```bash
# Verify the CloudFormation template
uv run cdk synth

# Deploy
uv run cdk deploy -c env=dev
```

**Note:** After a successful deployment, the terminal will output an **ApiEndpoint**. Copy this URL (e.g., `https://xyz.execute-api.eu-central-1.amazonaws.com/dev/`).

### 4. Register Webhook

Now, tell Telegram where to send updates. You must use the same secret you generated in Step 2.

**Option A: Manual Registration (Recommended)**

Replace the placeholders and run:

```bash
curl -F "url=<YOUR_API_ENDPOINT_FROM_STEP_3>/webhook" \
     -F "secret_token=<YOUR_SECRET_FROM_ENV>" \
     "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook"
```

**Option B: Using the Script (For Secret Rotation)**

The script in `scripts/setup_webhook.sh` can generate a new secret. If you use it, you must update your Lambda environment variable manually in the AWS Console afterwards.

---

## 🤖 Bot Commands

| Command   | Description                                                |
|-----------|------------------------------------------------------------|
| `/start`  | Restart the bot and view instructions.                     |
| `/help`   | Show usage guide and rules.                                |
| `/stats`  | (Admin) View community statistics and activity levels.     |
| `/support`| Get developer contact info.                                |

---

## ⚙️ CI/CD Setup (GitHub Actions)

This repository includes a GitHub Actions workflow for automated deployment. To use it, you must configure OpenID Connect (OIDC) trust between GitHub and AWS.

We provide a setup script to automate this:

```bash
# Usage: ./scripts/setup_oidc.sh <GITHUB_ORG/REPO>
# Example:
./scripts/setup_oidc.sh Bayashat/zerde-serverless-bot
```

**What this script does:**

* Creates an OIDC Provider in IAM (if missing).
* Creates an IAM Role (`GitHubAction-Deploy-TelegramBot`) that trusts your specific GitHub repository.
* Outputs the **AWS_ROLE_ARN** which you must add to your GitHub Repository Secrets.

---

## 🛠️ Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup (clone, uv, CDK, pre-commit) and PR process. For local testing from scratch (AWS account, new bot, token), see [Local Testing](docs/LOCAL_TESTING.md).

---

## 📄 License

This project is licensed under the **MIT License**.
