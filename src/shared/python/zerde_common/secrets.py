"""Lazy SSM Parameter Store batch loader for Lambda secrets."""

from __future__ import annotations

import os
from typing import Any

# Track which environment keys were loaded for each prefix in this execution environment.
_loaded_env_keys_by_prefix: dict[str, set[str]] = {}


def load_ssm_secrets_if_needed(
    ssm_prefix: str,
    ssm_name_to_env: dict[str, str],
) -> None:
    """Batch-load parameters into ``os.environ`` (once per ``ssm_prefix`` per cold start).

    No-op if ``ssm_prefix`` is empty (local / tests use plain environment variables).
    """
    p = ssm_prefix.strip()
    if not p:
        return
    loaded_env_keys = _loaded_env_keys_by_prefix.setdefault(p, set())
    pending = {
        ssm_name: env_key
        for ssm_name, env_key in ssm_name_to_env.items()
        if env_key not in loaded_env_keys and not os.environ.get(env_key)
    }
    if not pending:
        loaded_env_keys.update(ssm_name_to_env.values())
        return
    # Late import: keeps import-time off the critical path and avoids boto3 in tests
    # when prefix is set only in production.
    import boto3

    client: Any = boto3.client("ssm")
    names = [f"{p}/{k}" for k in pending]
    response = client.get_parameters(Names=names, WithDecryption=True)
    invalid = list(response.get("InvalidParameters", []))
    if invalid:
        raise OSError(
            "SSM get_parameters returned missing or disallowed parameters: "
            f"{invalid}. Check parameter names, IAM ssm:GetParameters, and KMS decrypt."
        )
    for param in response.get("Parameters", []):
        full_name: str = param.get("Name", "")
        short = full_name.removeprefix(f"{p}/")
        if env_key := pending.get(short):
            os.environ[env_key] = param.get("Value", "")
            loaded_env_keys.add(env_key)
