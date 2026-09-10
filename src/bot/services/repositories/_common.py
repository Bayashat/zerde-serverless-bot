"""Shared DynamoDB resource (lazy singleton)."""

import boto3

_dynamodb_resource = None


def get_dynamodb():
    """Return a shared boto3 DynamoDB resource, creating it lazily."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb")
    from services.memory_v2.cost_meter import register_client

    register_client(_dynamodb_resource.meta.client)
    return _dynamodb_resource
