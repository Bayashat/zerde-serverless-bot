"""Shared Python Lambda layer (``/opt/python/zerde_common``)."""

from __future__ import annotations

from aws_cdk import IgnoreMode
from aws_cdk import aws_lambda as _lambda
from components.constants import LAMBDA_RUNTIME, LAYER_ASSET_EXCLUDES, PROJECT_ROOT
from constructs import Construct


def add_zerde_common_layer(
    scope: Construct,
    construct_id: str = "ZerdeCommonLayer",
) -> _lambda.ILayerVersion:
    """Layer at ``src/shared`` → ``python/zerde_common`` (AWS Lambda standard layout)."""
    return _lambda.LayerVersion(
        scope,
        construct_id,
        code=_lambda.Code.from_asset(
            str(PROJECT_ROOT / "src" / "shared"), exclude=LAYER_ASSET_EXCLUDES, ignore_mode=IgnoreMode.GLOB
        ),
        layer_version_name="zerde-common",
        compatible_runtimes=[LAMBDA_RUNTIME],
        compatible_architectures=[_lambda.Architecture.ARM_64],
    )
