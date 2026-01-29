from aws_cdk import App, Environment
from stack import TelegramBotStack

app = App()

# Get environment name from context (default: dev)
env_name = app.node.try_get_context("env") or "dev"
env_config = Environment(account=app.node.try_get_context("account"), region=app.node.try_get_context("region"))

# Validate environment name
if env_name not in ["dev", "prod"]:
    raise ValueError(f"Invalid environment: {env_name}. Must be 'dev' or 'prod'")

# Create stack with environment-specific name
stack_name = f"TelegramBotStack-{env_name}"

# Initialize and deploy stack
TelegramBotStack(
    app,
    stack_name,
    env_name=env_name,
    env=env_config,
    description=f"Telegram Bot Infrastructure Stack - {env_name}",
)

app.synth()
