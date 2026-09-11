from pathlib import Path

from aws_cdk import aws_lambda as _lambda
from aws_cdk.aws_lambda_python_alpha import BundlingOptions

PROJECT_ROOT = Path(__file__).parent.parent.parent

LAMBDA_RUNTIME = _lambda.Runtime.PYTHON_3_13
# PythonFunction uses rsync patterns when copying first-party source, before pip
# installs dependencies. Never copy stale bytecode from a developer checkout.
LAMBDA_BUNDLING = BundlingOptions(asset_excludes=["__pycache__", "*.pyc", "*.pyo"])
LAYER_ASSET_EXCLUDES = ["**/__pycache__", "**/__pycache__/**", "**/*.pyc", "**/*.pyo"]

CONSTRUCT_PREFIX = "ZerdeServerless"
RESOURCE_PREFIX = "zerde-serverless"
