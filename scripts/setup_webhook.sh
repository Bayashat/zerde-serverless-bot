#!/bin/bash

# Usage:
# chmod +x scripts/setup_webhook.sh
# ./scripts/setup_webhook.sh [dev|prod] [bot_token] [webhook_url]

# NOTE: webhook_url should be the API Gateway URL with the /webhook path

BOT_TOKEN=$1
SECRET_TOKEN=$2
WEBHOOK_URL=$3

if [ -z "$3" ]; then
  echo "Usage: ./setup_webhook.sh [bot_token] [secret_token] [webhook_url]"
  exit 1
fi


echo "🚀 Setting up Webhook..."
echo ""

# Set webhook with generated secret token
RESPONSE=$(curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=$WEBHOOK_URL" \
     -d "secret_token=$SECRET_TOKEN" \
     -d "drop_pending_updates=true" \
     -d 'allowed_updates=["message","callback_query"]')

echo "📡 Webhook response:"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
