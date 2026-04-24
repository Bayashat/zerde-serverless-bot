from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Stack
from components import BotConstruct, MessagingConstruct, NewsConstruct, QuizConstruct
from components.constants import CONSTRUCT_PREFIX, RESOURCE_PREFIX
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
        quiz_llm_rpd = os.environ.get("QUIZ_LLM_RPD", "20")
        wtf_gemini_model = os.environ.get("WTF_GEMINI_MODEL")
        news_gemini_model = os.environ.get("NEWS_GEMINI_MODEL")
        quiz_gemini_model = os.environ.get("QUIZ_GEMINI_MODEL")

        # ── Groq parameters ──────────────────────────────────────────────────
        groq_api_base = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
        groq_model = os.environ.get("GROQ_MODEL")

        # ── DeepSeek parameters ────────────────────────────────────────────────
        deepseek_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        deepseek_model = os.environ.get("DEEPSEEK_MODEL")

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
        chat_lang_map = {cid: lang for lang, cids in all_chats_union.items() for cid in cids}

        # ── Constructs ─────────────────────────────────────────────────────────
        messaging = MessagingConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Messaging",
            env_name=env_name,
            is_prod=is_prod,
        )

        bot = BotConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Bot",
            env_name=env_name,
            is_prod=is_prod,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            default_lang=default_lang,
            ssm_secret_prefix=ssm_secret_prefix,
            queue=messaging.queue,
            admin_user_id=admin_user_id,
            gemini_api_base=gemini_api_base,
            wtf_gemini_model=wtf_gemini_model,
            gemini_rpd_limit=gemini_rpd_limit,
            groq_api_base=groq_api_base,
            groq_model=groq_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_model=deepseek_model,
            chat_lang_map=chat_lang_map,
            captcha_timeout_seconds=captcha_timeout_seconds,
            captcha_max_attempts=captcha_max_attempts,
            kick_ban_duration_seconds=kick_ban_duration_seconds,
            voteban_threshold=voteban_threshold,
            voteban_forgive_threshold=voteban_forgive_threshold,
        )

        NewsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}News",
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
            env_name=env_name,
            is_prod=is_prod,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            quiz_gemini_model=quiz_gemini_model,
            ssm_secret_prefix=ssm_secret_prefix,
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

        # ── Outputs ────────────────────────────────────────────────────────────
        CfnOutput(
            self,
            f"{CONSTRUCT_PREFIX}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{RESOURCE_PREFIX}-webhook-api-url-{env_name}",
            value=bot.api.url,
        )
