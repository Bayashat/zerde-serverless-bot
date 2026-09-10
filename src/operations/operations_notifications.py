"""Allowlisted operational transitions, never arbitrary Telegram destinations/text."""

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import urllib3
from zerde_common.secrets import load_ssm_secrets_if_needed

_http = urllib3.PoolManager(timeout=urllib3.Timeout(total=10), retries=False)


@dataclass(frozen=True)
class Notice:
    stream: str
    observed_at: int
    text: str


def _timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Notification timestamp must have a timezone")
    return int(parsed.timestamp() * 1000)


def parse_notice(record: dict, *, now: float | None = None) -> Notice | None:
    now = time.time() if now is None else now
    sns = record.get("Sns") or {}
    if record.get("EventSource") != "aws:sns" or sns.get("TopicArn") != os.environ["OPERATIONS_TOPIC_ARN"]:
        raise ValueError("Untrusted notification source")
    sent = _timestamp(sns["Timestamp"])
    if not sns.get("MessageId") or sent > (now + 300) * 1000:
        raise ValueError("Invalid notification envelope")
    message = json.loads(sns["Message"])
    env = os.environ["ENVIRONMENT"]
    if "AlarmName" in message:
        name = message["AlarmName"]
        allowed = json.loads(os.environ["OPERATIONS_ALARM_NAMES"])
        account = os.environ["OPERATIONS_ACCOUNT_ID"]
        region = os.environ["AWS_REGION"]
        arn = f"arn:aws:cloudwatch:{region}:{account}:alarm:{name}"
        if name not in allowed or message.get("AWSAccountId") != account or message.get("AlarmArn") != arn:
            raise ValueError("Unregistered alarm")
        state = message.get("NewStateValue")
        if state != "ALARM" and not (state == "OK" and message.get("OldStateValue") == "ALARM"):
            return None
        observed = _timestamp(message["StateChangeTime"])
        text = f"ZerdeBot {env}: {'故障' if state == 'ALARM' else '恢复'}\n{name}"
        stream = arn
    else:
        if (
            message.get("schema") != "zerde.operations.v1"
            or message.get("kind") != "budget"
            or message.get("project") != "ZerdeBot"
            or message.get("environment") != env
            or message.get("component") != "memory-v2"
            or message.get("budget_scope") not in {"model", "incremental_aws"}
            or type(message.get("threshold_percent")) is not int
            or message["threshold_percent"] not in {80, 90, 100}
            or message.get("status") not in {"warning", "paused"}
            or not re.fullmatch(r"\d{4}-\d{2}", message.get("period", ""))
        ):
            raise ValueError("Invalid budget event")
        observed = _timestamp(message["observed_at"])
        period = datetime.fromtimestamp(observed / 1000, timezone.utc).strftime("%Y-%m")
        if message["period"] != period:
            raise ValueError("Budget period differs from observation")
        scope = message["budget_scope"]
        threshold = message["threshold_percent"]
        status = message["status"]
        label = "全项目模型" if scope == "model" else "Memory V2 增量 AWS"
        text = (
            f"ZerdeBot 项目预算（触发环境：{env}）\n{label} {period}\n"
            f"{threshold}% · {status}\n金额及暂停状态以预算 owner 的账本为准；AWS 项为增量估算。"
        )
        stream = f"budget:{env}:{scope}:{period}"
    if observed > (now + 300) * 1000 or observed > sent + 300_000:
        raise ValueError("Notification observation is in the future")
    # Retained/dead-letter events are reviewed manually after this freshness window.
    if observed < (now - 7 * 86400) * 1000 or sent < (now - 7 * 86400) * 1000:
        raise ValueError("Notification expired; inspect recovery runbook")
    return Notice(stream, observed, text)


def send_private(text: str) -> None:
    admin = os.environ.get("ADMIN_USER_ID", "")
    if not admin.isdecimal() or int(admin) <= 0:
        raise ValueError("A positive private ADMIN_USER_ID is required")
    load_ssm_secrets_if_needed(os.environ.get("SSM_SECRET_PREFIX", ""), {"bot-token": "BOT_TOKEN"})
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Operations bot token is unavailable")
    # Keep this endpoint fixed: configuration cannot redirect the credential.
    response = _http.request(
        "POST",
        f"https://api.telegram.org/bot{token}/sendMessage",
        body=json.dumps({"chat_id": int(admin), "text": text}).encode(),
        headers={"Content-Type": "application/json"},
        retries=False,
    )
    if response.status != 200:
        raise RuntimeError(f"Operations Telegram HTTP {response.status}")
    payload = json.loads(response.data)
    result = payload.get("result") or {}
    if payload.get("ok") is not True or not result.get("message_id"):
        raise RuntimeError("Operations Telegram delivery was not confirmed")
    if result.get("chat", {}).get("type") != "private" or result["chat"].get("id") != int(admin):
        raise RuntimeError("Operations Telegram destination was not confirmed")
