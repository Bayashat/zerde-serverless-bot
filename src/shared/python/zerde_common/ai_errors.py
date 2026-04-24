"""Provider-level errors that may justify retry or secondary-model fallback."""

from __future__ import annotations


class ZerdeProviderError(Exception):
    """Base class for external LLM / API failures (rate limits, transport, bad payloads)."""


class ProviderRateLimitError(ZerdeProviderError):
    """HTTP 429 or provider-specific quota / rate limit."""


class ProviderTransportError(ZerdeProviderError):
    """Timeouts, connection errors, HTTP 5xx, broken TLS."""


class ProviderResponseError(ZerdeProviderError):
    """Unparseable body, empty response, MAX_TOKENS JSON truncation, provider schema violation."""


def map_http_status_to_provider_error(
    status: int,
    message: str,
) -> ZerdeProviderError:
    """Map a REST error status to a small provider error taxonomy (for urllib3/requests)."""
    if status == 429:
        return ProviderRateLimitError(message)
    if status >= 500:
        return ProviderTransportError(message)
    return ProviderResponseError(message)
