from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from aws_cdk import CfnOutput, Stack
from components import BotConstruct, MessagingConstruct, NewsConstruct
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

        bot_token = _require("TELEGRAM_BOT_TOKEN")
        webhook_secret_token = _require("TELEGRAM_WEBHOOK_SECRET_TOKEN")
        news_chat_ids = _require("NEWS_CHAT_IDS")
        gemini_api_key = _require("GEMINI_API_KEY")

        default_lang = os.environ.get("DEFAULT_LANG", "kk")
        telegram_api_base = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org/bot")
        ai_provider = os.environ.get("AI_PROVIDER", "gemini")
        llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")

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
            news_chat_ids=news_chat_ids,
            ai_provider=ai_provider,
            llm_model=llm_model,
            log_level=log_level,
        )

        # ── Outputs ────────────────────────────────────────────────────────────
        CfnOutput(
            self,
            f"{CONSTRUCT_PREFIX}WebhookApiUrl",
            description="API Gateway URL for the Telegram webhook",
            export_name=f"{RESOURCE_PREFIX}-webhook-api-url-{env_name}",
            value=bot.api.url,
        )
