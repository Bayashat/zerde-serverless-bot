# Zerde Bot

[English](../README.md) | [Қазақша](README_kk.md) | [Русский](README_ru.md)

![Python](https://img.shields.io/badge/Python-3.13-blue.svg)
![uv](https://img.shields.io/badge/uv-Managed-purple.svg?logo=python)
![AWS Lambda](https://img.shields.io/badge/AWS_Lambda-Serverless-ff9900.svg?logo=awslambda&logoColor=white)
![DynamoDB](https://img.shields.io/badge/Amazon_DynamoDB-NoSQL-4053D6.svg?logo=amazondynamodb&logoColor=white)
![S3 Vectors](https://img.shields.io/badge/S3_Vectors-RAG_memory-569A31.svg?logo=amazons3&logoColor=white)
![Google Gemini](https://img.shields.io/badge/Google_Gemini-AI-8E75B2.svg?logo=googlegemini&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Zerde** — IT қауымдастықтарына арналған serverless Telegram боты. Бұрын ол қарапайым LLM wrapper және moderation bot болатын; қазіргі бағыты — **RAG жады бар agentic group-chat bot**. Ол `/ask` сұрақтарына жауап береді, reply thread-ті түсінеді, топ контекстін есте сақтайды, ұзақ мерзімді memory-ден релевант ақпарат іздейді және чатқа қашан араласу дұрыс екенін бағалайды.

Бот әлі де captcha, anti-spam, voteban, күнделікті AI news digest және IT quiz функцияларын атқарады. Бірақ негізгі жаңа қабат — group memory және agent behavior.

---

## Не өзгерді?

Zerde енді тек “соңғы хабарламаны LLM-ге жіберетін” бот емес. Қазір онда:

- **Recent memory**: command емес топ хабарламалары DynamoDB-де `MSG#...` ретінде сақталады.
- **User profiles**: әр адамның өз хабарламаларынан алынған жеңіл profile.
- **Long-term memory**: candidate-gated және budgeted structured extraction арқылы алынатын `EVENT#...`, `USER_FACT#...`, `GROUP_FACT#...`, `JOKE#...`, `DAILY_SUMMARY#...`, rule fallback бар.
- **Hybrid RAG**: long-term memory Gemini embedding арқылы S3 Vectors semantic retrieval-ге түседі, ал DynamoDB lexical fallback және local reranking exact терминдерді ұстайды.
- **Agent behavior**: `/ask`, @mention, self-reference grounding, bot жауабына reply follow-up, conservative proactive reply gating, жауап ұзындығын басқару, `/agent why` source summary.
- **Memory controls**: `/memory`, `/agent`, `/memory about me`, `/memory forget me`, `/memory forget this` related vector cleanup-пен, owner-only group cleanup.

RAG дегеніміз — **Retrieval-Augmented Generation**: алдымен релевант memory/document іздеу, содан кейін LLM-ге сол контекстпен жауап бергізу. Zerde-де RAG — үлкенірек agentic bot архитектурасының бір қабаты.

---

## Негізгі мүмкіндіктер

| Мүмкіндік | Сипаттама |
|----------|-----------|
| Group-chat agent | `/ask`, @mention және bot жауабына reply арқылы қойылған сұрақтарға requester/recent/profile/long-term/lexical/semantic memory контекстімен жауап береді. |
| RAG memory | Group memory DynamoDB-де сақталады, long-term memory structured Gemini schema + rule fallback арқылы алынады, high-information memory S3 Vectors semantic retrieval үшін индекстеледі және exact-term DynamoDB fallback + local reranking қолданылады. |
| Reply thread continuity | Bot жауаптары `AGENT_REPLY#...` ретінде сақталады, сондықтан follow-up сұрақтар алдыңғы жауапты біледі. |
| Social timing | Proactive жауаптар local heuristics, recent bot penalty, Gemini decision және daily limit арқылы өтеді. |
| Captcha және anti-spam | Жаңа мүшелерді тексеру, rule-based және Groq арқылы spam тексеру. |
| Community voteban | `/voteban` арқылы қауымдастық дауысымен ban/forgive. |
| Daily AI news | EventBridge арқылы іске қосылатын news Lambda Gemini/DeepSeek-compatible жолдармен IT news digest жасайды. |
| IT quizzes | Scheduled және on-demand quiz Lambda көптілді developer quiz жібереді. |
| Serverless ops | AWS CDK Lambda, API Gateway, DynamoDB, SQS, EventBridge, S3 Vectors, IAM және alarms ресурстарын басқарады. |

---

## Архитектура

```mermaid
flowchart LR
  TG["Telegram groups"] --> APIGW["HTTP API Gateway"]
  APIGW --> BOT["Bot Lambda<br/>webhook + SQS worker"]

  BOT --> STATS[("DynamoDB<br/>stats / captcha / votes")]
  BOT --> MEMORY[("DynamoDB<br/>group memory")]
  BOT --> MAINQ["SQS timeout/tasks queue"]
  MAINQ --> BOT

  BOT --> VQ["SQS vector memory queue"]
  VQ --> BOT
  BOT --> S3V["S3 Vectors<br/>semantic memory index"]

  BOT --> GEMINI["Gemini<br/>agent replies / summaries / embeddings"]
  BOT --> GROQ["Groq<br/>spam checks"]

  EB["EventBridge schedules"] --> NEWS["News Lambda"]
  EB --> QUIZ["Quiz Lambda"]
  NEWS --> GEMINI
  QUIZ --> GEMINI
  NEWS --> TG
  QUIZ --> TG

  LAYER["Shared Lambda layer<br/>zerde_common"] -.-> BOT
  LAYER -.-> NEWS
  LAYER -.-> QUIZ
```

| Компонент | Trigger | Міндеті |
|-----------|---------|---------|
| `src/bot/` | API Gateway + SQS | Telegram webhook, captcha, voteban, spam screening, `/ask`, agent replies, memory writes, vector indexing tasks. |
| `src/news/` | EventBridge | Көптілді IT news digest. |
| `src/quiz/` | EventBridge + bot invoke | Scheduled және on-demand developer quizzes. |
| `src/shared/python/zerde_common/` | Lambda layer | Ортақ config, secret loading, logging, redaction, provider error helpers. |
| `infra/` | CDK | Serverless infrastructure, queues, tables, vector bucket/index, alarms, Lambda wiring. |

Толығырақ developer map: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Bot командалары

| Команда | Кімге | Сипаттама |
|---------|------|-----------|
| `/start` | Барлығына | Ботты қайта бастау және нұсқаулық көру. |
| `/help` | Барлығына | Командалар мен ережелер. |
| `/ping` | Барлығына | Health check. |
| `/support` | Барлығына | Developer contact. |
| `/stats` | Admins | Community статистикасы. |
| `/voteban` | Барлығына | Reply арқылы ban vote бастау. |
| `/quizstats` | Барлығына | Жеке quiz score, streak, rank. |
| `/ask <question>` | Memory қосылған топтарда | Agent-ке сұрақ қою; басқа хабарламаға reply ретінде де қолдануға болады және “мен кіммін” сияқты сұрақтарды requester identity арқылы түсінеді. |
| `/memory about me` | Барлығына | Current user-дің өз хабарламаларынан сақталған profile fields көрсету; басқа адамдардың бағасын көрсетпейді. |
| `/memory on/off/status/forget ...` | Settings үшін group owner немесе bot owner; users өз memory өшіре алады | Group memory басқару және cleanup. `forget this` reply жасалған bot answer/source message-ке байланысты memory өшіреді, vector cleanup configured болса бірге жүреді. |
| `/agent on/off/status/why` | Group owner немесе bot owner | Agent participation басқару және bot неге жауап бергенін көру; memory source түрлері/count көрсетіледі, толық memory text көрсетілмейді. `/agent off` proactive, mention және reply-thread қатысуын өшіреді; жад қосулы болса, `/ask` қолжетімді. |

---

## Әзірлеу

```bash
uv sync --frozen
uv run pytest tests/ -q
uv run pre-commit run --all-files
```

Infra тексеру:

```bash
cd infra
uv run cdk synth -c env=dev
uv run cdk diff -c env=dev
```

Setup үшін [CONTRIBUTING.md](../CONTRIBUTING.md), толық AWS + Telegram walkthrough үшін [LOCAL_TESTING.md](LOCAL_TESTING.md) қараңыз.

---

## Тарих

Zerde бастапқыда [serverless-tg-bot-starter](https://github.com/Bayashat/serverless-tg-bot-starter) негізінде жасалған. Ол starter қарапайым serverless Telegram bot үшін әлі де пайдалы. Бұл репозиторий кейін memory-enabled agentic bot, news және quiz workload-тары бар толық жүйеге айналды.

---

## License

MIT License.
