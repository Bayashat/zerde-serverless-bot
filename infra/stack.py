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

        def _require(key: str) -> str:
            value = os.environ.get(key)
            if not value:
                raise ValueError(f"{key} must be set in environment")
            return value

        def _parse_chat_ids(key: str) -> list[str]:
            value = os.environ.get(key, "")
            return [cid.strip() for cid in value.split(",") if cid.strip()]

        # ── Parameters ──────────────────────────────────────────────────────────
        default_lang = os.environ.get("DEFAULT_LANG", "kk")
        ai_provider = os.environ.get("AI_PROVIDER", "gemini")

        telegram_api_base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")

        # ── Timing parameters ──────────────────────────────────────────────────
        captcha_timeout_seconds = os.environ.get("CAPTCHA_TIMEOUT_SECONDS", "60")
        kick_ban_duration_seconds = os.environ.get("KICK_BAN_DURATION_SECONDS", "31")

        # ── Vote-to-ban thresholds ──────────────────────────────────────────
        voteban_threshold = os.environ.get("VOTEBAN_THRESHOLD", "7")
        voteban_forgive_threshold = os.environ.get("VOTEBAN_FORGIVE_THRESHOLD", "7")

        # ── Bot parameters ────────────────────────────────────────────────────
        bot_token = _require("TELEGRAM_BOT_TOKEN")
        webhook_secret_token = _require("TELEGRAM_WEBHOOK_SECRET_TOKEN")

        # ── Gemini parameters ──────────────────────────────────────────────────
        gemini_api_base = os.environ.get("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta/models")
        gemini_rpd_limit = os.environ.get("GEMINI_RPD_LIMIT", "500")
        quiz_llm_rpd = os.environ.get("QUIZ_LLM_RPD", "20")
        wtf_gemini_model = os.environ.get("WTF_GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        gemini_model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")

        # ── Groq parameters ──────────────────────────────────────────────────
        groq_api_base = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
        groq_api_key = os.environ.get("GROQ_API_KEY", "")
        groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

        # ── Llama parameters ──────────────────────────────────────────────────
        llama_api_base = os.environ.get("LLAMA_API_BASE", "https://api.llama.com/v1")
        llama_model = os.environ.get("LLAMA_MODEL", "Llama-4-Scout-17B-16E-Instruct-FP8")
        llama_api_key = os.environ.get("LLAMA_API_KEY", "")

        # ── DeepSeek parameters ────────────────────────────────────────────────
        deepseek_api_base = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")

        # ── Fallback model ────────────────────────────────────────────────────
        fallback_model = os.environ.get("FALLBACK_MODEL", "gemini-2.5-flash")
        wtf_fallback_provider = os.environ.get("WTF_FALLBACK_PROVIDER", "deepseek")

        chats: dict[str, list[str]] = {
            "kk": _parse_chat_ids("CHATS_KK"),
            "zh": _parse_chat_ids("CHATS_ZH"),
            "ru": _parse_chat_ids("CHATS_RU"),
        }

        admin_user_id = os.environ.get("ADMIN_USER_ID", "")

        # Build chat_id → lang mapping for the bot lambda
        chat_lang_map = {cid: lang for lang, cids in chats.items() for cid in cids}

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
            bot_token=bot_token,
            webhook_secret_token=webhook_secret_token,
            queue=messaging.queue,
            admin_user_id=admin_user_id,
            gemini_api_base=gemini_api_base,
            gemini_api_key=gemini_api_key,
            wtf_gemini_model=wtf_gemini_model,
            gemini_rpd_limit=gemini_rpd_limit,
            groq_api_base=groq_api_base,
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            llama_api_base=llama_api_base,
            llama_api_key=llama_api_key,
            llama_model=llama_model,
            deepseek_api_base=deepseek_api_base,
            deepseek_api_key=deepseek_api_key,
            deepseek_model=deepseek_model,
            wtf_fallback_provider=wtf_fallback_provider,
            chat_lang_map=chat_lang_map,
            captcha_timeout_seconds=captcha_timeout_seconds,
            kick_ban_duration_seconds=kick_ban_duration_seconds,
            voteban_threshold=voteban_threshold,
            voteban_forgive_threshold=voteban_forgive_threshold,
        )

        NewsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}News",
            env_name=env_name,
            is_prod=is_prod,
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            chats=chats,
            ai_provider=ai_provider,
            llm_model=gemini_model,
            fallback_model=fallback_model,
            log_level=log_level,
        )

        quiz = QuizConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Quiz",
            env_name=env_name,
            is_prod=is_prod,
            log_level=log_level,
            telegram_api_base=telegram_api_base,
            ai_provider=ai_provider,
            gemini_model=gemini_model,
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            groq_api_base=groq_api_base,
            groq_api_key=groq_api_key,
            groq_model=groq_model,
            quiz_llm_rpd=quiz_llm_rpd,
            chats=chats,
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
