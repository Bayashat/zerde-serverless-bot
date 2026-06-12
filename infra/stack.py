from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Stack
from components import BotConstruct, MessagingConstruct, NewsConstruct, QuizConstruct, VectorIndexerConstruct
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
from components.observability import (
    add_lambda_operational_alarms,
    add_sqs_dlq_visible_alarm,
)
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

        def _parse_chat_ids(key: str) -> list[str]:
            value = os.environ.get(key, "")
            return [cid.strip() for cid in value.split(",") if cid.strip()]

        # ── Parameters ──────────────────────────────────────────────────────────
        default_lang = os.environ.get("DEFAULT_LANG", "kk")
        telegram_api_base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")

        # ── Timing parameters ──────────────────────────────────────────────────
        captcha_timeout_seconds = os.environ.get("CAPTCHA_TIMEOUT_SECONDS", "120")
        kick_ban_duration_seconds = os.environ.get("KICK_BAN_DURATION_SECONDS", "31")
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
        gemini_embedding_rpd_limit = os.environ.get("GEMINI_EMBEDDING_RPD_LIMIT", "1000")
        quiz_llm_rpd = os.environ.get("QUIZ_LLM_RPD", "20")
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        news_gemini_model = os.environ.get("NEWS_GEMINI_MODEL", "gemini-3.1-flash-lite")
        quiz_gemini_model = os.environ.get("QUIZ_GEMINI_MODEL", "gemini-3.1-flash-lite")

        # ── Groq parameters ──────────────────────────────────────────────────
        groq_api_base = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
        groq_model = os.environ.get("GROQ_MODEL")
        spam_rule_enforce_threshold = os.environ.get("SPAM_RULE_ENFORCE_THRESHOLD", "0.8")
        spam_rule_ai_threshold = os.environ.get("SPAM_RULE_AI_THRESHOLD", "0.15")
        spam_ai_confidence_threshold = os.environ.get("SPAM_AI_CONFIDENCE_THRESHOLD", "0.85")

        # ── DeepSeek parameters ────────────────────────────────────────────────
        deepseek_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

        # ── Group memory / agent MVP ─────────────────────────────────────────
        legacy_group_memory_retention_days = os.environ.get("GROUP_MEMORY_RETENTION_DAYS")

        def _memory_retention_days_env(name: str, default_days: str, *, legacy_fallback: bool = True) -> str:
            fallback = legacy_group_memory_retention_days if legacy_fallback else None
            return os.environ.get(name, fallback or default_days)

        group_memory_enabled = os.environ.get("GROUP_MEMORY_ENABLED", "true")
        group_memory_recent_limit = os.environ.get("GROUP_MEMORY_RECENT_LIMIT", "300")
        group_memory_retention_days = legacy_group_memory_retention_days or "3650"
        group_memory_raw_message_retention_days = _memory_retention_days_env(
            "GROUP_MEMORY_RAW_MESSAGE_RETENTION_DAYS", "30"
        )
        group_memory_agent_reply_retention_days = _memory_retention_days_env(
            "GROUP_MEMORY_AGENT_REPLY_RETENTION_DAYS", "7", legacy_fallback=False
        )
        group_memory_long_term_retention_days = _memory_retention_days_env(
            "GROUP_MEMORY_LONG_TERM_RETENTION_DAYS", group_memory_retention_days
        )
        group_memory_daily_summary_retention_days = _memory_retention_days_env(
            "GROUP_MEMORY_DAILY_SUMMARY_RETENTION_DAYS", group_memory_retention_days
        )
        group_memory_proactive_counter_retention_days = _memory_retention_days_env(
            "GROUP_MEMORY_PROACTIVE_COUNTER_RETENTION_DAYS", "3", legacy_fallback=False
        )
        group_memory_extractor_provider = os.environ.get("GROUP_MEMORY_EXTRACTOR_PROVIDER", "gemini")
        group_memory_extractor_mode = os.environ.get("GROUP_MEMORY_EXTRACTOR_MODE", "gemini_candidate_only")
        group_memory_extractor_min_confidence = os.environ.get("GROUP_MEMORY_EXTRACTOR_MIN_CONFIDENCE", "0.65")
        group_memory_extractor_daily_llm_limit = os.environ.get("GROUP_MEMORY_EXTRACTOR_DAILY_LLM_LIMIT", "50")
        group_memory_extractor_per_chat_daily_limit = os.environ.get(
            "GROUP_MEMORY_EXTRACTOR_PER_CHAT_DAILY_LIMIT", "20"
        )
        group_memory_daily_summary_days = os.environ.get("GROUP_MEMORY_DAILY_SUMMARY_DAYS", "7")
        group_memory_daily_summary_message_limit = os.environ.get("GROUP_MEMORY_DAILY_SUMMARY_MESSAGE_LIMIT", "500")
        agent_enabled = os.environ.get("AGENT_ENABLED", "true")
        agent_bot_username = os.environ.get("AGENT_BOT_USERNAME", "@zerde_kz_bot")
        agent_recent_context_limit = os.environ.get("AGENT_RECENT_CONTEXT_LIMIT", "100")
        agent_daily_proactive_limit = os.environ.get("AGENT_DAILY_PROACTIVE_LIMIT", "3")
        agent_proactive_score_threshold = os.environ.get("AGENT_PROACTIVE_SCORE_THRESHOLD", "0.62")
        agent_proactive_final_threshold = os.environ.get("AGENT_PROACTIVE_FINAL_THRESHOLD", "0.72")
        vector_memory_enabled = os.environ.get("VECTOR_MEMORY_ENABLED", "true")
        vector_memory_provider = os.environ.get("VECTOR_MEMORY_PROVIDER", "s3_vectors")
        vector_memory_dimensions = os.environ.get("VECTOR_MEMORY_DIMENSIONS", "768")
        vector_memory_embedding_model = os.environ.get("VECTOR_MEMORY_EMBEDDING_MODEL", "gemini-embedding-2")
        vector_memory_index_throttle_seconds = os.environ.get("VECTOR_MEMORY_INDEX_THROTTLE_SECONDS", "3")
        vector_memory_backfill_batch_size = os.environ.get("VECTOR_MEMORY_BACKFILL_BATCH_SIZE", "50")
        vector_memory_max_distance = os.environ.get("VECTOR_MEMORY_MAX_DISTANCE", "0.85")
        vector_memory_vector_bucket_name = os.environ.get("VECTOR_MEMORY_VECTOR_BUCKET_NAME")
        vector_memory_index_name = os.environ.get("VECTOR_MEMORY_INDEX_NAME")

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
        )

        bot = BotConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Bot",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            default_lang=default_lang,
            ssm_secret_prefix=ssm_secret_prefix,
            queue=messaging.queue,
            vector_queue=messaging.vector_queue,
            admin_user_id=admin_user_id,
            gemini_api_base=gemini_api_base,
            gemini_model=gemini_model,
            gemini_rpd_limit=gemini_rpd_limit,
            gemini_embedding_rpd_limit=gemini_embedding_rpd_limit,
            groq_api_base=groq_api_base,
            groq_model=groq_model,
            spam_rule_enforce_threshold=spam_rule_enforce_threshold,
            spam_rule_ai_threshold=spam_rule_ai_threshold,
            spam_ai_confidence_threshold=spam_ai_confidence_threshold,
            chat_lang_map=chat_lang_map,
            captcha_timeout_seconds=captcha_timeout_seconds,
            captcha_max_attempts=captcha_max_attempts,
            kick_ban_duration_seconds=kick_ban_duration_seconds,
            voteban_threshold=voteban_threshold,
            voteban_forgive_threshold=voteban_forgive_threshold,
            group_memory_enabled=group_memory_enabled,
            group_memory_recent_limit=group_memory_recent_limit,
            group_memory_retention_days=group_memory_retention_days,
            group_memory_raw_message_retention_days=group_memory_raw_message_retention_days,
            group_memory_agent_reply_retention_days=group_memory_agent_reply_retention_days,
            group_memory_long_term_retention_days=group_memory_long_term_retention_days,
            group_memory_daily_summary_retention_days=group_memory_daily_summary_retention_days,
            group_memory_proactive_counter_retention_days=group_memory_proactive_counter_retention_days,
            group_memory_extractor_provider=group_memory_extractor_provider,
            group_memory_extractor_mode=group_memory_extractor_mode,
            group_memory_extractor_min_confidence=group_memory_extractor_min_confidence,
            group_memory_extractor_daily_llm_limit=group_memory_extractor_daily_llm_limit,
            group_memory_extractor_per_chat_daily_limit=group_memory_extractor_per_chat_daily_limit,
            group_memory_daily_summary_days=group_memory_daily_summary_days,
            group_memory_daily_summary_message_limit=group_memory_daily_summary_message_limit,
            agent_enabled=agent_enabled,
            agent_bot_username=agent_bot_username,
            agent_recent_context_limit=agent_recent_context_limit,
            agent_daily_proactive_limit=agent_daily_proactive_limit,
            agent_proactive_score_threshold=agent_proactive_score_threshold,
            agent_proactive_final_threshold=agent_proactive_final_threshold,
            vector_memory_enabled=vector_memory_enabled,
            vector_memory_provider=vector_memory_provider,
            vector_memory_dimensions=vector_memory_dimensions,
            vector_memory_embedding_model=vector_memory_embedding_model,
            vector_memory_index_throttle_seconds=vector_memory_index_throttle_seconds,
            vector_memory_backfill_batch_size=vector_memory_backfill_batch_size,
            vector_memory_max_distance=vector_memory_max_distance,
            vector_memory_vector_bucket_name=vector_memory_vector_bucket_name,
            vector_memory_index_name=vector_memory_index_name,
        )

        vector_indexer = VectorIndexerConstruct(
            self,
            f"{CONSTRUCT_PREFIX}VectorIndexer",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            ssm_secret_prefix=ssm_secret_prefix,
            vector_queue=messaging.vector_queue,
            memory_table=bot.memory_table,
            stats_table=bot.stats_table,
            vector_bucket=bot.vector_bucket,
            vector_index=bot.vector_index,
            environment=bot.bot_environment,
        )

        news = NewsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}News",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
            ssm_secret_prefix=ssm_secret_prefix,
            chats=news_chats,
            news_gemini_model=news_gemini_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_model=deepseek_model,
            log_level=log_level,
        )

        quiz = QuizConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Quiz",
            shared_layer=zerde_layer,
            env_name=env_name,
            is_prod=is_prod,
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

        # ── CloudWatch alarms (no SNS action — view / subscribe in AWS console) ─
        add_lambda_operational_alarms(
            self,
            env_name=env_name,
            logical_slug="bot",
            fn=bot.handler_lambda,
            duration_p95_threshold_ms=80_000,
        )
        add_lambda_operational_alarms(
            self,
            env_name=env_name,
            logical_slug="vector-indexer",
            fn=vector_indexer.handler_lambda,
            duration_p95_threshold_ms=240_000,
        )
        add_lambda_operational_alarms(
            self,
            env_name=env_name,
            logical_slug="news",
            fn=news.news_lambda,
            duration_p95_threshold_ms=240_000,
        )
        add_lambda_operational_alarms(
            self,
            env_name=env_name,
            logical_slug="quiz",
            fn=quiz.quiz_lambda,
            duration_p95_threshold_ms=48_000,
        )
        add_sqs_dlq_visible_alarm(
            self,
            env_name=env_name,
            logical_slug="timeout-tasks",
            dlq=messaging.dlq,
        )
        add_sqs_dlq_visible_alarm(
            self,
            env_name=env_name,
            logical_slug="vector-memory-tasks",
            dlq=messaging.vector_dlq,
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        CfnOutput(
            self,
            f"{CONSTRUCT_PREFIX}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{RESOURCE_PREFIX}-webhook-api-url-{env_name}",
            value=bot.api.url,
        )
