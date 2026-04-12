"""LambdaInvoker: invokes another Lambda function synchronously."""

import json

import boto3
from core.logger import LoggerAdapter, get_logger

logger = LoggerAdapter(get_logger(__name__), {})


class LambdaInvoker:
    """Thin wrapper around boto3 Lambda client for synchronous invocation."""

    def __init__(self) -> None:
        self._client = boto3.client("lambda")

    def invoke(self, function_name: str, payload: dict) -> dict:
        """Invoke *function_name* synchronously with *payload*.

        Returns the parsed JSON response or an empty dict on failure.
        """
        try:
            response = self._client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode(),
            )
            raw = response["Payload"].read()
            return json.loads(raw) if raw else {}
        except Exception:
            logger.error(
                "Lambda invocation failed",
                extra={"function_name": function_name},
                exc_info=True,
            )
            return {}

    def invoke_async(self, function_name: str, payload: dict) -> bool:
        """Invoke *function_name* asynchronously with *payload*.

        Returns True when invocation was accepted by Lambda.
        """
        try:
            self._client.invoke(
                FunctionName=function_name,
                InvocationType="Event",
                Payload=json.dumps(payload).encode(),
            )
            return True
        except Exception:
            logger.error(
                "Async Lambda invocation failed",
                extra={"function_name": function_name},
                exc_info=True,
            )
            return False
