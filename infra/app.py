from aws_cdk import App
from stack import ZerdeTelegramBotStack

app = App()

env_name = app.node.try_get_context("env") or "dev"

if env_name not in ["dev", "prod"]:
    raise ValueError(f"Invalid environment: {env_name}. Must be 'dev' or 'prod'")

ZerdeTelegramBotStack(
    app,
    f"ZerdeServerlessTelegramBotStack-{env_name}",
    env_name=env_name,
    stack_name=f"zerde-serverless-telegram-bot-{env_name}",
    description=f"Zerde Serverless Telegram Bot Infrastructure Stack for {env_name}",
)

app.synth()
