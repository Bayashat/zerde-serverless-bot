# Local Testing Guide

This guide walks you through running Zerde Bot end-to-end: creating an AWS account, creating a Telegram bot, configuring all tokens, and deploying for testing.

---

## 1. Create an AWS Account (If You Don't Have One)

1. Go to [aws.amazon.com](https://aws.amazon.com) and choose **Create an AWS Account**.
2. Complete sign-up (email, password, account type, payment method, identity verification).
   **Note:** The AWS Free Tier is sufficient for all three Lambda functions; you will not be charged under normal testing loads.
3. Sign in to the **AWS Management Console**.
4. (Recommended) Create an IAM user for day-to-day use instead of the root user:
   - **IAM** → **Users** → **Create user** (e.g. `zerde-dev`).
   - Attach **AdministratorAccess** (simplest for testing) or a custom policy covering Lambda, API Gateway, DynamoDB, SQS, IAM, EventBridge, CloudFormation.
   - Create an **Access key** for "Command Line Interface (CLI)" and save the Access Key ID and Secret Access Key.
5. Configure the AWS CLI:

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
   - **Name** (e.g. "My Zerde Test Bot") — shown to users.
   - **Username** (e.g. `my_zerde_test_bot`) — must end in `bot`, must be unique.
4. BotFather will reply with a **token** like:

   ```
   123456789:ABCdefGHIjkLMNopqrsTUVwxyz
   ```

5. **Save this token** — you will use it as `TELEGRAM_BOT_TOKEN`. Do not share it or commit it to git.

Optional: Create a test group, add your bot as admin with "Delete messages" and "Restrict members" permissions to test the captcha and kick flows. Add it to a second group to test the quiz.

---

## 3. Get External API Keys

Zerde uses two external APIs beyond Telegram:

### Google Gemini (for News and Quiz translation)

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with a Google account.
2. Create an API key. Copy it — this is your `GEMINI_API_KEY`.
3. Free tier is sufficient for daily digest volumes.

### QuizAPI (for Daily Tech Quiz)

1. Go to [quizapi.io](https://quizapi.io) and register a free account.
2. Generate an API key in your dashboard. Copy it — this is your `QUIZAPI_KEY`.
3. The free plan covers the daily quiz volume.

---

## 4. Configure the Project

Ensure you have completed the [development setup](../CONTRIBUTING.md) (clone, uv, CDK CLI, `uv sync`).

```bash
cp .env.example .env
```

Generate a webhook secret:

```bash
openssl rand -hex 32
```

Edit `.env` and fill in all required values:

```ini
# Required
TELEGRAM_BOT_TOKEN=<token from BotFather>
TELEGRAM_WEBHOOK_SECRET_TOKEN=<hex string from openssl above>
GEMINI_API_KEY=<your Gemini API key>
QUIZAPI_KEY=<your QuizAPI key>

# Optional — configure chat IDs to receive news/quiz
NEWS_CHATS_KK=<comma-separated chat IDs for Kazakh news>
NEWS_CHATS_ZH=<comma-separated chat IDs for Chinese news>
NEWS_CHATS_RU=<comma-separated chat IDs for Russian news>
QUIZ_CHATS=<comma-separated chat IDs for daily quiz>

# Optional — defaults shown
AI_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
DEFAULT_LANG=kk
```

**To find a group's chat ID:** Add [@userinfobot](https://t.me/userinfobot) to the group; it will print the chat ID on join.

Never commit `.env` — it is in `.gitignore`.

---

## 5. Deploy the Stack to AWS

```bash
# Synthesize CloudFormation (optional validation step)
uv run cdk synth -c env=dev

# Deploy all three Lambdas + infrastructure
uv run cdk deploy -c env=dev
```

When prompted to approve IAM changes, type `y`.

After a successful deploy, the terminal prints an **ApiEndpoint** URL (e.g. `https://xxxx.execute-api.eu-central-1.amazonaws.com/dev/`). Copy it.

The deploy creates:
- **Bot Lambda** — API Gateway webhook endpoint + SQS queue
- **News Lambda** — EventBridge rules (only active in `prod` env)
- **Quiz Lambda** — EventBridge rule at 08:00 UTC + DynamoDB quiz table (only active in `prod` env)
- **DynamoDB** — stats table (joins/bans) + quiz table (scores/leaderboard)

> EventBridge schedules are only created when deploying with `-c env=prod`. For local testing, invoke the News and Quiz Lambdas manually from the AWS Console or CLI.

---

## 6. Register the Webhook with Telegram

Telegram must send updates to your API Gateway URL.

**Option A — Manual (recommended for first time):**

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

---

## 7. Test the Bot

1. Open Telegram and find your bot by username (e.g. `@my_zerde_test_bot`).
2. Send `/start` — you should get a reply.
3. Send `/ping` — confirms the Lambda is reachable.
4. Add the bot to a test group as admin and trigger a join to test captcha flow.
5. Reply to any message with `/voteban` to test the vote-to-ban flow.

**To test the Quiz Lambda manually:**

In the AWS Console → Lambda → `zerde-serverless-quiz-dev` → Test, use this event payload:

```json
{ "chat_ids": ["<your_test_chat_id>"] }
```

**To inspect logs:**

- AWS Console → **CloudWatch** → **Log groups**
- `/aws/lambda/zerde-serverless-bot-dev` — Bot Lambda
- `/aws/lambda/zerde-serverless-news-dev` — News Lambda
- `/aws/lambda/zerde-serverless-quiz-dev` — Quiz Lambda

---

## 8. Tear Down (Optional)

```bash
uv run cdk destroy -c env=dev
```

Then unset the webhook so Telegram stops sending updates:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
```

---

## Summary Checklist

| Step | What you need |
|------|----------------|
| AWS | Account + IAM user with CLI access (`aws configure`) |
| Telegram | Bot created via @BotFather, token saved |
| Gemini | API key from [aistudio.google.com](https://aistudio.google.com) |
| QuizAPI | API key from [quizapi.io](https://quizapi.io) |
| Project | Clone, uv, CDK CLI, `uv sync`, `.env` with all required keys |
| Deploy | `uv run cdk deploy -c env=dev` |
| Webhook | `setWebhook` with API endpoint and same secret as in `.env` |
| Test | Chat with bot and/or test in a group |

For contribution workflow (branching, pre-commit, PRs), see [CONTRIBUTING.md](../CONTRIBUTING.md).
