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

        bot_token = _require("TELEGRAM_BOT_TOKEN")
        webhook_secret_token = _require("TELEGRAM_WEBHOOK_SECRET_TOKEN")
        gemini_api_key = _require("GEMINI_API_KEY")
        news_chats: dict[str, list[str]] = {
            "kk": _parse_chat_ids("NEWS_CHATS_KK"),
            "zh": _parse_chat_ids("NEWS_CHATS_ZH"),
            "ru": _parse_chat_ids("NEWS_CHATS_RU"),
        }

        default_lang = os.environ.get("DEFAULT_LANG", "kk")
        telegram_api_base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
        ai_provider = os.environ.get("AI_PROVIDER", "gemini")
        llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
        quizapi_key = _require("QUIZAPI_KEY")
        quiz_chats = _parse_chat_ids("QUIZ_CHATS")

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
            queue=messaging.queue,
            bot_token=bot_token,
            webhook_secret_token=webhook_secret_token,
            telegram_api_base=telegram_api_base,
            default_lang=default_lang,
            log_level=log_level,
        )

        NewsConstruct(
            self,
            f"{CONSTRUCT_PREFIX}News",
            env_name=env_name,
            is_prod=is_prod,
            bot_token=bot_token,
            gemini_api_key=gemini_api_key,
            news_chats=news_chats,
            ai_provider=ai_provider,
            llm_model=llm_model,
            log_level=log_level,
        )

        quiz = QuizConstruct(
            self,
            f"{CONSTRUCT_PREFIX}Quiz",
            env_name=env_name,
            is_prod=is_prod,
            bot_token=bot_token,
            quizapi_key=quizapi_key,
            gemini_api_key=gemini_api_key,
            ai_provider=ai_provider,
            llm_model=llm_model,
            quiz_chats=quiz_chats,
            log_level=log_level,
        )

        # Grant Bot Lambda access to quiz table and inject env var
        quiz.quiz_table.grant_read_write_data(bot.handler_lambda)
        bot.handler_lambda.add_environment("QUIZ_TABLE_NAME", quiz.quiz_table.table_name)

        # ── Outputs ────────────────────────────────────────────────────────────
        CfnOutput(
            self,
            f"{CONSTRUCT_PREFIX}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{RESOURCE_PREFIX}-webhook-api-url-{env_name}",
            value=bot.api.url,
        )
