from pathlib import Path

from aws_cdk import aws_lambda as _lambda

PROJECT_ROOT = Path(__file__).parent.parent.parent

LAMBDA_RUNTIME = _lambda.Runtime.PYTHON_3_13

CONSTRUCT_PREFIX = "ZerdeServerless"
RESOURCE_PREFIX = "zerde-serverless"
