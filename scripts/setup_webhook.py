"""Register Telegram updates without dropping pending messages or exposing secrets."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, urlopen

REQUIRED_UPDATES = ("message", "edited_message", "callback_query", "poll_answer")


class WebhookSetupError(RuntimeError):
    pass


def telegram_call(token, method, payload):
    request = Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
        if result.get("ok") is not True:
            raise ValueError("Telegram did not confirm the operation")
        return result["result"]
    except Exception:
        # HTTP/transport errors can contain the credential-bearing URL.
        raise WebhookSetupError(
            f"Telegram {method} was not confirmed; inspect current webhook before retrying"
        ) from None


def configure_webhook(token, secret, url, *, call=telegram_call):
    if not token or not secret or not url.startswith("https://"):
        raise WebhookSetupError("BOT_TOKEN, WEBHOOK_SECRET_TOKEN and an HTTPS WEBHOOK_URL are required")
    before = call(token, "getWebhookInfo", {})
    if not isinstance(before, dict) or not isinstance(before.get("url", ""), str):
        raise WebhookSetupError("Existing webhook configuration is malformed")
    if before.get("url") and before["url"] != url:
        raise WebhookSetupError("Existing webhook URL differs; refusing to move a configured bot to another endpoint")
    updates = before.get("allowed_updates", [])
    maximum = before.get("max_connections", 40)
    if not isinstance(updates, list) or not all(isinstance(item, str) for item in updates):
        raise WebhookSetupError("Existing update subscription is malformed")
    if type(maximum) is not int or not 1 <= maximum <= 100:
        raise WebhookSetupError("Existing connection limit is malformed")
    # An empty subscription means Telegram's default set. Preserve that default
    # instead of narrowing it to this bot's four currently required update types.
    allowed = list(dict.fromkeys([*updates, *REQUIRED_UPDATES])) if updates else []
    payload = {
        "url": url,
        "secret_token": secret,
        "allowed_updates": allowed,
        "max_connections": maximum,
        "drop_pending_updates": False,
    }
    if call(token, "setWebhook", payload) is not True:
        raise WebhookSetupError("Telegram setWebhook was not confirmed; inspect current webhook before retrying")
    after = call(token, "getWebhookInfo", {})
    if (
        not isinstance(after, dict)
        or not isinstance(after.get("allowed_updates", []), list)
        or not all(isinstance(item, str) for item in after.get("allowed_updates", []))
        or after.get("url") != url
        or after.get("max_connections") != maximum
        or set(after.get("allowed_updates", [])) != set(allowed)
    ):
        raise WebhookSetupError("Webhook readback differs from the requested configuration")
    return {
        "verified": True,
        "allowed_updates": allowed,
        "max_connections": maximum,
        "pending_update_count": after.get("pending_update_count"),
        "pending_updates_dropped": False,
    }


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args and len(args) != 3:
        print("Usage: setup_webhook.sh [bot_token secret_token webhook_url]", file=sys.stderr)
        return 2
    values = args or [os.environ.get(name, "") for name in ("BOT_TOKEN", "WEBHOOK_SECRET_TOKEN", "WEBHOOK_URL")]
    try:
        result = configure_webhook(*values)
    except WebhookSetupError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
