# Local Testing Guide

This guide walks you through running Zerde Bot end-to-end: creating an AWS account, creating a Telegram bot, configuring tokens, and deploying for testing.

---

## 1. Create an AWS Account (If You Don’t Have One)

1. Go to [aws.amazon.com](https://aws.amazon.com) and choose **Create an AWS Account**.
2. Complete sign-up (email, password, account type, payment method, identity verification).
   **Note:** Free tier is enough for this bot; you will not be charged if you stay within Lambda/API Gateway free tier limits.
3. Sign in to the **AWS Management Console**.
4. (Recommended) Create an IAM user for day-to-day use instead of using the root user:
   - **IAM** → **Users** → **Create user** (e.g. `zerde-dev`).
   - Attach policy **AdministratorAccess** (for simplicity when testing) or a custom policy that allows Lambda, API Gateway, DynamoDB, SQS, IAM, CloudFormation.
   - Create **Access key** for “Command Line Interface (CLI)” and save the **Access Key ID** and **Secret Access Key**.
5. Configure the AWS CLI on your machine:

```bash
aws configure
```

Enter the Access Key ID, Secret Access Key, and a default region (e.g. `eu-central-1` or `us-east-1`).

Verify:

```bash
aws sts get-caller-identity
```

---

## 2. Create a Telegram Bot and Get the Token

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`.
3. Follow the prompts:
   - **Name** (e.g. “My Zerde Test Bot”) — shown to users.
   - **Username** (e.g. `my_zerde_test_bot`) — must end in `bot`, must be unique.
4. BotFather will reply with a **token** like:

   ```
   123456789:ABCdefGHIjkLMNopqrsTUVwxyz
   ```

5. **Save this token**; you will use it as `TELEGRAM_BOT_TOKEN`. Do not share it or commit it to git.

Optional: create a test group, add your bot as an admin (with “Delete messages” and “Restrict members” if you want to test captcha/kick), and optionally use `/setdescription` and `/setabouttext` in BotFather for your test bot.

---

## 3. Configure the Project

Ensure you have completed the [development setup](CONTRIBUTING.md) (clone, uv, CDK CLI, `uv sync`).

1. Copy the example env file:

```bash
cp .env.example .env
```

2. Generate a webhook secret (used to validate that requests to your webhook really come from Telegram):

```bash
openssl rand -hex 32
```

3. Edit `.env` and set:

```ini
TELEGRAM_BOT_TOKEN=<paste the token from BotFather>
TELEGRAM_WEBHOOK_SECRET_TOKEN=<paste the 32-byte hex string you generated>
```

Never commit `.env`; it is listed in `.gitignore`.

---

## 4. Deploy the Stack to AWS

From the project root:

```bash
# Synthesize CloudFormation (optional check)
uv run cdk synth -c env=dev

# Deploy (creates/updates Lambda, API Gateway, DynamoDB, SQS, etc.)
uv run cdk deploy -c env=dev
```

When prompted to approve IAM changes, type `y`.
After a successful deploy, the terminal will print an **ApiEndpoint** (e.g. `https://xxxx.execute-api.eu-central-1.amazonaws.com/dev/`). Copy this URL.

---

## 5. Register the Webhook with Telegram

Telegram must send updates to your API Gateway URL. Use the **same** `TELEGRAM_WEBHOOK_SECRET_TOKEN` you put in `.env` (and that CDK passed to the Lambda).

**Option A — Manual (recommended for first time):**

Replace the placeholders and run:

```bash
curl -F "url=<YOUR_API_ENDPOINT>/webhook" \
     -F "secret_token=<YOUR_TELEGRAM_WEBHOOK_SECRET_TOKEN>" \
     "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook"
```

Example:

```bash
curl -F "url=https://abc123.execute-api.eu-central-1.amazonaws.com/dev/webhook" \
     -F "secret_token=your_hex_secret_from_env" \
     "https://api.telegram.org/bot123456789:ABCdef.../setWebhook"
```

**Option B — Script:**

```bash
./scripts/setup_webhook.sh dev <YOUR_BOT_TOKEN> <YOUR_API_ENDPOINT>/webhook
```

The script generates a **new** secret and prints it. If you use it, you must update the Lambda environment variable `TELEGRAM_WEBHOOK_SECRET_TOKEN` in the AWS Console (or redeploy with the new value in `.env`) so it matches.

---

## 6. Test the Bot

1. Open Telegram and find your bot by its username (e.g. `@my_zerde_test_bot`).
2. Send `/start` — you should get a reply.
3. Add the bot to a test group, make it an admin, and trigger a join (e.g. invite another account or use a second bot) to test captcha and stats if needed.

To inspect logs:

- **AWS Console** → **Lambda** → select the **Receiver** or **Worker** function → **Monitor** → **View logs in CloudWatch**.

---

## 7. Tear Down (Optional)

To delete all resources created by the stack:

```bash
uv run cdk destroy -c env=dev
```

Then unset the webhook so Telegram stops sending updates to your URL:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
```

---

## Summary Checklist

| Step | What you need |
|------|----------------|
| AWS | Account + IAM user with CLI access (`aws configure`) |
| Telegram | Bot created via @BotFather, token saved |
| Project | Clone, uv, CDK CLI, `uv sync`, `.env` with token + webhook secret |
| Deploy | `uv run cdk deploy -c env=dev` |
| Webhook | `setWebhook` with API endpoint and same secret as in `.env` |
| Test | Chat with bot and/or test in a group |

For contribution workflow (branching, pre-commit, PRs), see [CONTRIBUTING.md](../CONTRIBUTING.md).
