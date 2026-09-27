from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Stack, Tags
from components import BotConstruct, MessagingConstruct, NewsConstruct, QuizConstruct
from components.background_recovery import add_background_recovery
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
from components.memory_cost import MemoryCostConstruct
from components.memory_v2 import MemoryV2Construct
from components.memory_worker import MemoryWorkerConstruct, grant_project_budget
from components.observability import add_lambda_operational_alarms, add_sqs_dlq_visible_alarm
from components.operations import OperationsConstruct
from components.zerde_layer import add_zerde_common_layer
from constructs import Construct
from dotenv import load_dotenv


class ZerdeTelegramBotStack(Stack):
    """CDK stack: wires together Messaging, Bot, and News constructs."""

    def __init__(self, scope: Construct, construct_id: str, env_name: str = "dev", **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        is_prod = env_name == "prod"
        log_level = "INFO" if is_prod else "DEBUG"

        project_root = Path(__file__).parent.parent
        load_dotenv(dotenv_path=project_root / ".env")
        dev_runtime_enabled = os.environ.get("DEV_RUNTIME_ENABLED", "false").lower()
        if dev_runtime_enabled not in {"true", "false"}:
            raise ValueError("DEV_RUNTIME_ENABLED must be true or false")
        self.runtime_active = is_prod or dev_runtime_enabled == "true"
        Tags.of(self).add("Project", "ZerdeBot")
        Tags.of(self).add("Environment", env_name)
        Tags.of(self).add("Component", "shared")

        def _parse_chat_ids(key: str) -> list[str]:
            value = os.environ.get(key, "")
            return [cid.strip() for cid in value.split(",") if cid.strip()]

        def _parse_int_env(key: str, default: int, *, min_value: int, max_value: int) -> int:
            raw = os.environ.get(key)
            try:
                value = int(raw) if raw else default
            except ValueError:
                value = default
            return max(min_value, min(max_value, value))

        # ── Parameters ──────────────────────────────────────────────────────────
        default_lang = os.environ.get("DEFAULT_LANG", "kk")
        telegram_api_base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")

        # ── SQS operational retention ─────────────────────────────────────────
        main_task_queue_retention_days = _parse_int_env(
            "MAIN_TASK_QUEUE_RETENTION_DAYS",
            1,
            min_value=1,
            max_value=14,
        )
        main_task_dlq_retention_days = _parse_int_env(
            "MAIN_TASK_DLQ_RETENTION_DAYS",
            14,
            min_value=1,
            max_value=14,
        )
        main_task_dlq_retention_days = max(main_task_dlq_retention_days, main_task_queue_retention_days)

        # ── Timing parameters ──────────────────────────────────────────────────
        captcha_timeout_seconds = os.environ.get("CAPTCHA_TIMEOUT_SECONDS", "120")
        kick_ban_duration_seconds = str(max(60, int(os.environ.get("KICK_BAN_DURATION_SECONDS", "60"))))
        captcha_max_attempts = os.environ.get("CAPTCHA_MAX_ATTEMPTS", "3")

        # ── Vote-to-ban thresholds ──────────────────────────────────────────
        voteban_threshold = os.environ.get("VOTEBAN_THRESHOLD", "7")
        voteban_forgive_threshold = os.environ.get("VOTEBAN_FORGIVE_THRESHOLD", "7")

        # ── SSM secret prefix (secrets live in Parameter Store, not here) ────
        # Path: /zerde/{env_name}/<secret-name>  — stored once, read at Lambda runtime.
        ssm_secret_prefix = f"/zerde/{env_name}"

        # ── Gemini parameters ──────────────────────────────────────────────────
        gemini_api_base = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
        gemini_rpd_limit = os.environ.get("GEMINI_RPD_LIMIT", "500")
        quiz_llm_rpd = os.environ.get("QUIZ_LLM_RPD", "20")
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        news_gemini_model = os.environ.get("NEWS_GEMINI_MODEL", "gemini-3.1-flash-lite")
        quiz_gemini_model = os.environ.get("QUIZ_GEMINI_MODEL", "gemini-3.1-flash-lite")

        # ── Groq parameters ──────────────────────────────────────────────────
        groq_api_base = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
        groq_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
        groq_spam_model = os.environ.get("GROQ_SPAM_MODEL", "openai/gpt-oss-safeguard-20b")
        spam_rule_enforce_threshold = os.environ.get("SPAM_RULE_ENFORCE_THRESHOLD", "0.8")
        spam_rule_ai_threshold = os.environ.get("SPAM_RULE_AI_THRESHOLD", "0.15")
        spam_ai_confidence_threshold = os.environ.get("SPAM_AI_CONFIDENCE_THRESHOLD", "0.85")
        spam_review_admin_mentions = os.environ.get("SPAM_REVIEW_ADMIN_MENTIONS", "{}")

        # ── DeepSeek parameters ────────────────────────────────────────────────
        deepseek_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        # Explicit bot identity and requested media.
        agent_bot_username = os.environ.get("AGENT_BOT_USERNAME", "@zerde_kz_bot")
        agent_bot_id = os.environ.get("AGENT_BOT_ID", "")
        multimodal_enabled = os.environ.get("MULTIMODAL_ENABLED", "true")
        multimodal_max_download_bytes = os.environ.get("MULTIMODAL_MAX_DOWNLOAD_BYTES", "12000000")
        multimodal_inline_max_bytes = os.environ.get("MULTIMODAL_INLINE_MAX_BYTES", "8000000")
        multimodal_text_file_max_chars = os.environ.get("MULTIMODAL_TEXT_FILE_MAX_CHARS", "20000")

        # Shared chats used for bot's chat→lang routing (union of all feature chats)
        bot_chats: dict[str, list[str]] = {
            "kk": _parse_chat_ids("CHATS_KK"),
            "zh": _parse_chat_ids("CHATS_ZH"),
            "ru": _parse_chat_ids("CHATS_RU"),
        }

        # Per-feature chat overrides; fall back to shared bot_chats if not set
        news_chats: dict[str, list[str]] = {
            "kk": _parse_chat_ids("NEWS_CHATS_KK") or bot_chats["kk"],
            "zh": _parse_chat_ids("NEWS_CHATS_ZH") or bot_chats["zh"],
            "ru": _parse_chat_ids("NEWS_CHATS_RU") or bot_chats["ru"],
        }

        quiz_chats: dict[str, list[str]] = {
            "kk": _parse_chat_ids("QUIZ_CHATS_KK") or bot_chats["kk"],
            "zh": _parse_chat_ids("QUIZ_CHATS_ZH") or bot_chats["zh"],
            "ru": _parse_chat_ids("QUIZ_CHATS_RU") or bot_chats["ru"],
        }

        admin_user_id = os.environ.get("ADMIN_USER_ID", "")

        # Build chat_id → lang mapping for the bot lambda (covers all feature chats)
        all_chats_union: dict[str, set[str]] = {"kk": set(), "zh": set(), "ru": set()}
        for feature_chats in (bot_chats, news_chats, quiz_chats):
            for lang, cids in feature_chats.items():
                all_chats_union[lang].update(cids)
        chat_lang_map = {cid: lang for lang, cids in all_chats_union.items() for cid in sorted(cids)}

        # ── Constructs ─────────────────────────────────────────────────────────
        zerde_layer = add_zerde_common_layer(self, f"{CONSTRUCT_PREFIX}ZerdeCommonLayer")

        messaging = MessagingConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Messaging",
            env_name=env_name,
            is_prod=is_prod,
            main_queue_retention_days=main_task_queue_retention_days,
            main_dlq_retention_days=main_task_dlq_retention_days,
        )

        bot = BotConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Bot",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            runtime_active=self.runtime_active,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            default_lang=default_lang,
            ssm_secret_prefix=ssm_secret_prefix,
            queue=messaging.queue,
            admin_user_id=admin_user_id,
            gemini_api_base=gemini_api_base,
            gemini_model=gemini_model,
            gemini_rpd_limit=gemini_rpd_limit,
            groq_api_base=groq_api_base,
            groq_model=groq_model,
            groq_spam_model=groq_spam_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_model=deepseek_model,
            spam_rule_enforce_threshold=spam_rule_enforce_threshold,
            spam_rule_ai_threshold=spam_rule_ai_threshold,
            spam_ai_confidence_threshold=spam_ai_confidence_threshold,
            spam_review_admin_mentions=spam_review_admin_mentions,
            chat_lang_map=chat_lang_map,
            captcha_timeout_seconds=captcha_timeout_seconds,
            captcha_max_attempts=captcha_max_attempts,
            kick_ban_duration_seconds=kick_ban_duration_seconds,
            voteban_threshold=voteban_threshold,
            voteban_forgive_threshold=voteban_forgive_threshold,
            agent_bot_username=agent_bot_username,
            agent_bot_id=agent_bot_id,
            multimodal_enabled=multimodal_enabled,
            multimodal_max_download_bytes=multimodal_max_download_bytes,
            multimodal_inline_max_bytes=multimodal_inline_max_bytes,
            multimodal_text_file_max_chars=multimodal_text_file_max_chars,
        )

        memory_v2 = MemoryV2Construct(self, f"{CONSTRUCT_PREFIX}MemoryV2", env_name=env_name, is_prod=is_prod)
        memory_v2.table.grant_read_write_data(bot.handler_lambda)
        bot.handler_lambda.add_environment("MEMORY_V2_TABLE_NAME", memory_v2.table.table_name)

        news = NewsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}News",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            runtime_active=self.runtime_active,
            ssm_secret_prefix=ssm_secret_prefix,
            chats=news_chats,
            news_gemini_model=news_gemini_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_model=deepseek_model,
            log_level=log_level,
            stats_table=bot.stats_table,
        )

        quiz = QuizConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Quiz",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            runtime_active=self.runtime_active,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            quiz_gemini_model=quiz_gemini_model,
            ssm_secret_prefix=ssm_secret_prefix,
            groq_api_base=groq_api_base,
            groq_model=groq_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_model=deepseek_model,
            quiz_llm_rpd=quiz_llm_rpd,
            chats=quiz_chats,
        )

        # Grant Bot Lambda access to quiz table and quiz lambda, inject env vars
        quiz.quiz_table.grant_read_write_data(bot.handler_lambda)
        bot.handler_lambda.add_environment("QUIZ_TABLE_NAME", quiz.quiz_table.table_name)
        quiz.quiz_lambda.grant_invoke(bot.handler_lambda)
        bot.handler_lambda.add_environment("QUIZ_LAMBDA_NAME", quiz.quiz_lambda.function_name)
        add_background_recovery(
            self,
            env_name=env_name,
            runtime_active=self.runtime_active,
            quiz_lambda=quiz.quiz_lambda,
            news_lambda=news.news_lambda,
            queue=messaging.queue,
            dlq=messaging.dlq,
        )

        # Independent notification transport, also reused by future worker owners.
        self.operations = OperationsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Operations",
            env_name=env_name,
            is_prod=is_prod,
            runtime_active=self.runtime_active,
            shared_layer=zerde_layer,
            stats_table=bot.stats_table,
            admin_user_id=os.environ.get("ADMIN_USER_ID", ""),
            ssm_secret_prefix=ssm_secret_prefix,
        )
        self.memory_worker = MemoryWorkerConstruct(
            self,
            f"{CONSTRUCT_PREFIX}MemoryWorker",
            env_name=env_name,
            is_prod=is_prod,
            runtime_active=self.runtime_active,
            shared_layer=zerde_layer,
            memory_table=memory_v2.table,
            stats_table=bot.stats_table,
            bot_environment=bot.bot_environment,
            operations=self.operations,
        )
        self.memory_worker.queue.grant_send_messages(bot.handler_lambda)
        bot.handler_lambda.add_environment("MEMORY_V2_QUEUE_URL", self.memory_worker.queue.queue_url)
        bot.handler_lambda.add_environment("MEMORY_BUDGET_TABLE_NAME", self.memory_worker.budget_table.table_name)
        bot.handler_lambda.add_environment("ENVIRONMENT", env_name)
        bot.handler_lambda.add_environment("OPERATIONS_TOPIC_ARN", self.operations.topic.topic_arn)
        grant_project_budget(bot.handler_lambda, self.memory_worker.budget_table)
        self.operations.grant_budget_publish(bot.handler_lambda)
        MemoryCostConstruct(
            self,
            "MemoryCost",
            bot_function=bot.handler_lambda,
            worker_function=self.memory_worker.handler_lambda,
            main_dlq=messaging.dlq,
            env_name=env_name,
            metering_started_at=int(os.environ.get("MEMORY_COST_METERING_STARTED_AT", "0") or "0"),
        )
        for construct, component in (
            (bot, "bot"),
            (news, "news"),
            (quiz, "quiz"),
            (messaging, "messaging"),
        ):
            Tags.of(construct).add("Component", component)
        if self.runtime_active:
            for slug, fn, duration in (
                ("bot", bot.handler_lambda, 80_000),
                ("news", news.news_lambda, 240_000),
                ("quiz", quiz.quiz_lambda, 48_000),
            ):
                for alarm in add_lambda_operational_alarms(
                    self,
                    env_name=env_name,
                    logical_slug=slug,
                    fn=fn,
                    duration_p95_threshold_ms=duration,
                ):
                    self.operations.register(alarm)
            for slug, dlq in (("timeout-tasks", messaging.dlq),):
                self.operations.register(
                    add_sqs_dlq_visible_alarm(
                        self,
                        env_name=env_name,
                        logical_slug=slug,
                        dlq=dlq,
                    )
                )

        # ── Outputs ────────────────────────────────────────────────────────────
        CfnOutput(
            self,
            f"{CONSTRUCT_PREFIX}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{RESOURCE_PREFIX}-webhook-api-url-{env_name}",
            value=bot.api.url,
        )
