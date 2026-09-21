#!/bin/bash
set -euo pipefail
# Prefer BOT_TOKEN, WEBHOOK_SECRET_TOKEN and WEBHOOK_URL environment variables.
# The historical three positional arguments remain supported.
exec python3 "$(dirname "$0")/setup_webhook.py" "$@"
