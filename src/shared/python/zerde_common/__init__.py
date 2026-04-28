"""Shared Lambda Layer utilities: typed env, secrets, logging, AI errors.

Kept free of business/domain logic so bot, news, and quiz stay decoupled.
"""

from zerde_common.ai_errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTransportError,
    ZerdeProviderError,
    map_http_status_to_provider_error,
)
from zerde_common.config import require, require_int, require_json
from zerde_common.logging_utils import (
    api_gateway_event_summary,
    llm_text_log_fields,
    truncate_log_text,
)
from zerde_common.secrets import load_ssm_secrets_if_needed

__all__ = [
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTransportError",
    "ZerdeProviderError",
    "map_http_status_to_provider_error",
    "api_gateway_event_summary",
    "llm_text_log_fields",
    "load_ssm_secrets_if_needed",
    "require",
    "require_int",
    "require_json",
    "truncate_log_text",
]
