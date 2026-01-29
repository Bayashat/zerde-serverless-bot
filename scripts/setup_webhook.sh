#!/bin/bash

# Usage:
# chmod +x scripts/setup_webhook.sh
# ./scripts/setup_webhook.sh [dev|prod] [bot_token] [webhook_url]

# NOTE: webhook_url should be the API Gateway URL with the /webhook path

ENV=$1
BOT_TOKEN=$2
WEBHOOK_URL=$3

if [ -z "$3" ]; then
  echo "Usage: ./setup_webhook.sh [dev|prod] [bot_token] [webhook_url]"
  exit 1
fi

# Generate secret token
SECRET_TOKEN=$(openssl rand -hex 32)

echo "🚀 Setting up Webhook for $ENV environment..."
echo "🔑 Generated secret token: $SECRET_TOKEN"
echo ""

# Set webhook with generated secret token
RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
     -d "url=$WEBHOOK_URL" \
     -d "secret_token=$SECRET_TOKEN" \
     -d "drop_pending_updates=true" \
     -d 'allowed_updates=["message","callback_query"]')

echo "📡 Webhook response:"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"

echo -e "\n\n✅ Webhook setup complete!"
echo "🔐 Secret Token (save this for your webhook configuration):"
echo "$SECRET_TOKEN"
