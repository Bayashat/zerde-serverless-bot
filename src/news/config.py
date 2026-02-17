"""News Lambda — centralised environment variable and secrets configuration."""

import os

import boto3


def _require_env(name: str) -> str:
    """Return the value of an environment variable or raise EnvironmentError."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Required environment variable '{name}' is not set")
    return value


def _get_secret(secret_name: str) -> str:
    """Retrieve a secret value from AWS Secrets Manager."""
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        if "SecretString" in response:
            return response["SecretString"]
        raise ValueError(f"Secret {secret_name} does not contain a string value")
    except Exception as e:
        raise EnvironmentError(f"Failed to retrieve secret '{secret_name}': {e}") from e


BOT_TOKEN: str = _require_env("BOT_TOKEN")
AI_PROVIDER: str = os.environ.get("AI_PROVIDER", "groq")

# NEWS_CHAT_ID supports comma-separated IDs: "-1001245,-1903430"
_parsed_chat_ids: list[str] = [cid.strip() for cid in _require_env("NEWS_CHAT_ID").split(",") if cid.strip()]
if not _parsed_chat_ids:
    raise ValueError("NEWS_CHAT_ID must contain at least one valid chat ID")
NEWS_CHAT_IDS: list[str] = _parsed_chat_ids

GROQ_API_KEY_SECRET_NAME = os.environ.get("GROQ_API_KEY_SECRET_NAME", "").strip()
_GROQ_API_KEY: str | None = None


def get_groq_api_key() -> str:
    global _GROQ_API_KEY
    if _GROQ_API_KEY is not None:
        return _GROQ_API_KEY

    if GROQ_API_KEY_SECRET_NAME:
        _GROQ_API_KEY = _get_secret(GROQ_API_KEY_SECRET_NAME)
    else:
        _GROQ_API_KEY = _require_env("GROQ_API_KEY")
    return _GROQ_API_KEY
