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

## 🤖 Bot Commands

| Command   | Description                                                |
|-----------|------------------------------------------------------------|
| `/start`  | Restart the bot and view instructions.                     |
| `/help`   | Show usage guide and rules.                                |
| `/stats`  | (Admin) View community statistics and activity levels.     |
| `/support`| Get developer contact info.                                |
| `/voteban`| Vote to ban a user.                                        |

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
