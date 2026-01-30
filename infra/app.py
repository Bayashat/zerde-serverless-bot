from aws_cdk import App, Environment
from stack import ZerdeTelegramBotStack

app = App()

env_name = app.node.try_get_context("env") or "dev"
env_config = Environment(account=app.node.try_get_context("account"), region=app.node.try_get_context("region"))

if env_name not in ["dev", "prod"]:
    raise ValueError(f"Invalid environment: {env_name}. Must be 'dev' or 'prod'")

stack_name = f"ZerdeTelegramBotStack-{env_name}"

ZerdeTelegramBotStack(
    app,
    stack_name,
    env_name=env_name,
    env=env_config,
    description=f"Zerde Telegram Bot Infrastructure Stack - {env_name}",
)

app.synth()
