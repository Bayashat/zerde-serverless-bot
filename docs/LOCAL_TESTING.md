# Local Testing Guide

This guide walks you through running Zerde Bot end-to-end: creating an AWS account, creating a Telegram bot, configuring all tokens, and deploying for testing.

---

## 1. Create an AWS Account (If You Don't Have One)

1. Go to [aws.amazon.com](https://aws.amazon.com) and choose **Create an AWS Account**.
2. Complete sign-up (email, password, account type, payment method, identity verification).
   **Note:** The AWS Free Tier is usually sufficient for light testing, but vector memory and LLM calls can create provider-side costs or quotas.
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

5. **Save this token** — you will use it as `BOT_TOKEN`. Do not share it or commit it to git.

Optional: Create a test group, add your bot as admin with "Delete messages" and "Restrict members" permissions to test captcha, kick, and full group-context flows. Disable BotFather privacy mode or keep the bot as admin so it can observe non-command group messages for memory.

---

## 3. Get External API Keys

Zerde can use three external APIs beyond Telegram:

### Google Gemini (for agent replies, memory summaries, embeddings, news, and quiz)

1. Go to [aistudio.google.com](https://aistudio.google.com) and sign in with a Google account.
2. Create an API key. Copy it — this is your `GEMINI_API_KEY`.
3. Free tier is usually sufficient for small tests.
4. Optional: use a separate key for `GEMINI_EMBEDDING_API_KEY`; if omitted, the bot can use `GEMINI_API_KEY`.

### Groq (for async spam checks)

1. Go to [console.groq.com](https://console.groq.com/) and create an API key.
2. Copy it — this is your `GROQ_API_KEY`.

### DeepSeek (optional fallback for quiz/news)

1. Go to [platform.deepseek.com](https://platform.deepseek.com/) and create an API key.
2. Copy it — this is your `DEEPSEEK_API_KEY`.

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
BOT_TOKEN=<token from BotFather>
WEBHOOK_SECRET_TOKEN=<hex string from openssl above>
GEMINI_API_KEY=<your Gemini API key>
GROQ_API_KEY=<your Groq API key>
DEEPSEEK_API_KEY=<your DeepSeek API key>

# Optional — configure chat IDs to receive news/quiz
CHATS_KK=<comma-separated chat IDs for Kazakh/default bot groups>
CHATS_ZH=<comma-separated chat IDs for Chinese bot groups>
CHATS_RU=<comma-separated chat IDs for Russian bot groups>
NEWS_CHATS_KK=<comma-separated chat IDs for Kazakh news>
NEWS_CHATS_ZH=<comma-separated chat IDs for Chinese news>
NEWS_CHATS_RU=<comma-separated chat IDs for Russian news>
QUIZ_CHATS_KK=<comma-separated chat IDs for Kazakh quiz>
QUIZ_CHATS_ZH=<comma-separated chat IDs for Chinese quiz>
QUIZ_CHATS_RU=<comma-separated chat IDs for Russian quiz>

# Optional — defaults shown
GEMINI_MODEL=gemini-3.1-flash-lite
NEWS_GEMINI_MODEL=gemini-3.1-flash-lite
QUIZ_GEMINI_MODEL=gemini-3.1-flash-lite
DEFAULT_LANG=kk
MAIN_TASK_QUEUE_RETENTION_DAYS=1
MAIN_TASK_DLQ_RETENTION_DAYS=14
VECTOR_MEMORY_QUEUE_RETENTION_DAYS=4
VECTOR_MEMORY_DLQ_RETENTION_DAYS=14

# Optional — group memory / agent
GROUP_MEMORY_ENABLED=true
GROUP_MEMORY_RETENTION_DAYS=3650
GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS=30
GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS=7
GROUP_MEMORY_LONG_TERM_RETENTION_DAYS=3650
GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS=3650
GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS=3
GROUP_MEMORY_EXTRACTOR_PROVIDER=gemini
GROUP_MEMORY_EXTRACTOR_MODE=gemini_candidate_only
GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE=0.65
GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT=50
GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT=20
VECTOR_MEMORY_ENABLED=true
VECTOR_MEMORY_PROVIDER=s3_vectors
VECTOR_MEMORY_SCHEMA_VERSION=1
VECTOR_MEMORY_MAX_DISTANCE=0.85
GEMINI_EMBEDDING_RPD_LIMIT=1000
AGENT_DAILY_PROACTIVE_LIMIT=3
AGENT_PROACTIVE_DELAY_SECONDS=45
AGENT_ENABLED=true
AGENT_BOT_USERNAME=@your_bot_username
AGENT_BOT_ID=
AGENT_RECENT_CONTEXT_LIMIT=100
```

**To find a group's chat ID:** Add [@userinfobot](https://t.me/userinfobot) to the group; it will print the chat ID on join.

Never commit `.env` — it is in `.gitignore`.

---

## 5. Deploy the Stack to AWS

```bash
# Synthesize CloudFormation (optional validation step)
uv run cdk synth -c env=dev

# Deploy Lambdas + queues + tables + optional S3 Vectors resources
uv run cdk deploy -c env=dev
```

When prompted to approve IAM changes, type `y`.

After a successful deploy, the terminal prints an **ApiEndpoint** URL (e.g. `https://xxxx.execute-api.eu-central-1.amazonaws.com/dev/`). Copy it.

The deploy creates:
- **Bot Lambda** — API Gateway webhook endpoint + main SQS worker for captcha, spam, `/ask`, group memory extraction, daily summaries, semantic retrieval, and vector cleanup/enqueue
- **Vector-indexer Lambda** — vector-memory SQS worker for `PROCESS_VECTOR_MEMORY` and `PROCESS_VECTOR_MEMORY_BACKFILL`
- **News Lambda** — EventBridge rules (only active in `prod` env)
- **Quiz Lambda** — EventBridge rule at 08:00 UTC + DynamoDB quiz table (only active in `prod` env)
- **DynamoDB** — stats table, group-memory table, and quiz table
- **SQS** — timeout/tasks queue consumed by the Bot Lambda plus vector-memory queue consumed by
  the Vector-indexer Lambda, each with DLQ. Defaults retain main tasks for 1 day, vector-memory
  tasks for 4 days, and DLQ messages for 14 days; tune with
  `MAIN_TASK_QUEUE_RETENTION_DAYS`, `MAIN_TASK_DLQ_RETENTION_DAYS`,
  `VECTOR_MEMORY_QUEUE_RETENTION_DAYS`, and `VECTOR_MEMORY_DLQ_RETENTION_DAYS`.
- **S3 Vectors** — vector bucket/index when `VECTOR_MEMORY_ENABLED=true` and provider is `s3_vectors`

> EventBridge schedules are only created when deploying with `-c env=prod`. For local testing, invoke the News and Quiz Lambdas manually from the AWS Console or CLI.

---

## 6. Register the Webhook with Telegram

Telegram must send updates to your API Gateway URL.

**Option A — Manual (recommended for first time):**

```bash
curl -F "url=<YOUR_API_ENDPOINT>/webhook" \
     -F "secret_token=<YOUR_WEBHOOK_SECRET_TOKEN>" \
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
6. In a group, run `/memory status` to confirm memory and vector status.
7. Run `/ask what is this chat discussing?` or reply to a message with `/ask` to test the group agent.
8. Reply to the bot's answer with a follow-up question to test `AGENT_REPLY#...` thread continuity. This should create short-term reply metadata only, not a vector memory task.

**To test the Quiz Lambda manually:**

In the AWS Console → Lambda → `zerde-serverless-quiz-dev` → Test, use this event payload:

```json
{ "chat_ids": ["<your_test_chat_id>"] }
```

**To inspect logs:**

- AWS Console → **CloudWatch** → **Log groups**
- `/aws/lambda/zerde-serverless-bot-dev` — Bot Lambda
- `/aws/lambda/zerde-serverless-vector-indexer-dev` — Vector-indexer Lambda
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
| Groq | API key from [console.groq.com](https://console.groq.com/) |
| Project | Clone, uv, CDK CLI, `uv sync`, `.env` with required keys and chat IDs |
| Deploy | `uv run cdk deploy -c env=dev` |
| Webhook | `setWebhook` with API endpoint and same secret as in `.env` |
| Test | Chat with bot, test captcha/voteban, `/memory status`, `/ask`, and reply-to-bot follow-ups |

For contribution workflow (branching, pre-commit, PRs), see [CONTRIBUTING.md](../CONTRIBUTING.md).
