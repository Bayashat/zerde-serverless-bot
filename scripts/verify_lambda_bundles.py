"""Import the real CDK assets in an ARM64 Lambda runtime, with networking disabled."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Captured from the public AWS Python 3.13 ARM64 runtime image; update deliberately.
RUNTIME_IMAGE = "public.ecr.aws/lambda/python@sha256:d52afe970081b30397342d019525dade26073d9e557fd94a3615de9b62ff9e27"
SYNTHETIC_ENV = {
    "AWS_DEFAULT_REGION": "eu-central-1",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_ACCESS_KEY_ID": "synthetic",
    "AWS_SECRET_ACCESS_KEY": "synthetic",
    "STATS_TABLE_NAME": "synthetic-stats",
    "MEMORY_TABLE_NAME": "synthetic-memory",
    "TABLE_NAME": "synthetic-quiz",
    "QUIZ_TABLE_NAME": "synthetic-quiz",
    "QUEUE_URL": "https://sqs.eu-central-1.amazonaws.com/000000000000/synthetic",
    "ADMIN_USER_ID": "1",
    "CHAT_LANG_MAP": "{}",
    "GEMINI_RPD_LIMIT": "500",
    "QUIZ_LLM_RPD": "20",
    "CAPTCHA_TIMEOUT_SECONDS": "120",
    "KICK_BAN_DURATION_SECONDS": "31",
    "CAPTCHA_MAX_ATTEMPTS": "3",
    "VOTEBAN_THRESHOLD": "7",
    "VOTEBAN_FORGIVE_THRESHOLD": "7",
    "LOG_LEVEL": "ERROR",
    "PYTHONPATH": "/var/task:/opt/python",
}
PROBE = """
import importlib, importlib.metadata, io, json, platform, sys
assert sys.version_info[:2] == (3, 13), sys.version
assert platform.machine() == 'aarch64', platform.machine()
expected = json.loads(sys.argv[1])
kind, handler = sys.argv[2:4]
for distribution in importlib.metadata.distributions(path=['/var/task']):
    name = distribution.metadata['Name'].lower().replace('_', '-')
    assert expected.get(name) == distribution.version, (name, distribution.version)
modules = ['boto3', 'botocore', 'urllib3']
if kind == 'bot':
    modules += ['PIL.Image']
else:
    modules += ['google.genai', 'pydantic_core', 'cryptography']
if kind == 'news':
    modules += ['feedparser']
for name in modules:
    module = importlib.import_module(name)
    assert module.__file__.startswith('/var/task/'), (name, module.__file__)
if kind == 'bot':
    from PIL import Image
    Image.new('RGB', (1, 1)).save(io.BytesIO(), format='PNG')
else:
    from cryptography.hazmat.primitives import hashes
    assert len(hashes.Hash(hashes.SHA256()).finalize()) == 32
module_name, function_name = handler.rsplit('.', 1)
assert callable(getattr(importlib.import_module(module_name), function_name))
print(json.dumps({'package': kind, 'handler': handler, 'architecture': platform.machine(),
    'python': platform.python_version(), 'boto3': importlib.metadata.version('boto3'),
    'urllib3': importlib.metadata.version('urllib3'), 'imports': 'passed', 'network': 'disabled'}))
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assembly", type=Path, default=ROOT / "infra/cdk.out")
    parser.add_argument("--image", default=RUNTIME_IMAGE)
    args = parser.parse_args()
    assembly = args.assembly.resolve()
    templates = list(assembly.glob("*.template.json"))
    if len(templates) != 1:
        raise SystemExit("Expected one freshly synthesized Zerde stack template")
    resources = json.loads(templates[0].read_text())["Resources"]
    functions = [resource for resource in resources.values() if resource["Type"] == "AWS::Lambda::Function"]
    if len(functions) != 4:
        raise SystemExit("Expected the bot, indexer, news and quiz Lambda assets")
    for function in functions:
        properties = function["Properties"]
        assert properties["Runtime"] == "python3.13" and properties["Architectures"] == ["arm64"]
        asset = assembly / function["Metadata"]["aws:asset:path"]
        if not (asset / "main.py").is_file():
            raise SystemExit("Lambda code has not been bundled; run real cdk synth first")
        layer_id = properties["Layers"][0]["Ref"]
        layer = assembly / resources[layer_id]["Metadata"]["aws:asset:path"] / "python"
        assert (layer / "zerde_common").is_dir()
        name = properties["FunctionName"]
        kind = "news" if "-news-" in name else "quiz" if "-quiz-" in name else "bot"
        expected = dict(re.findall(r"^([\w-]+)==([^\s;]+)", (ROOT / f"src/{kind}/requirements.txt").read_text(), re.M))
        command = [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--entrypoint",
            "python3",
            "--workdir",
            "/var/task",
            "--volume",
            f"{asset}:/var/task:ro",
            "--volume",
            f"{layer}:/opt/python:ro",
        ]
        for key, value in SYNTHETIC_ENV.items():
            command += ["--env", f"{key}={value}"]
        subprocess.run(
            command + [args.image, "-c", PROBE, json.dumps(expected), kind, properties["Handler"]], check=True
        )


if __name__ == "__main__":
    main()
