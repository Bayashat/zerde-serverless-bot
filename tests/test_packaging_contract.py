"""Prevent security floors and the checked-in Lambda locks drifting apart."""

import re
import tomllib
from pathlib import Path


def test_lambda_locks_include_the_complete_matching_sdk_and_hashes():
    locked = {package["name"]: package["version"] for package in tomllib.loads(Path("uv.lock").read_text())["package"]}
    for package in ("bot", "news", "quiz"):
        requirements = Path(f"src/{package}/requirements.txt").read_text()
        pins = dict(re.findall(r"^([\w-]+)==([^\s;]+)", requirements, re.MULTILINE))
        for dependency in ("boto3", "botocore", "urllib3"):
            assert pins[dependency] == locked[dependency]
        for name, version in pins.items():
            assert locked[name] == version
        logical_lines = requirements.replace("\\\n", " ").splitlines()
        for line in logical_lines:
            if line and not line.startswith("#"):
                assert "==" in line and "--hash=sha256:" in line
        assert "aws-cdk-lib" not in pins and "pytest" not in pins and "moto" not in pins
        assert ("pillow" in pins) == (package == "bot")
        assert ("google-genai" in pins) == (package in {"news", "quiz"})


def test_security_fixed_versions_and_ci_toolchain_remain_pinned():
    locked = {package["name"]: package["version"] for package in tomllib.loads(Path("uv.lock").read_text())["package"]}
    floors = {
        "pillow": "12.3.0",
        "urllib3": "2.7.0",
        "idna": "3.15",
        "pyasn1": "0.6.4",
        "cryptography": "50.0.0",
        "aws-cdk-lib": "2.253.0",
    }
    for package, floor in floors.items():
        assert tuple(map(int, locked[package].split("."))) >= tuple(map(int, floor.split(".")))
    for filename in ("deploy.yml", "pr_check.yml"):
        workflow = Path(".github/workflows", filename).read_text()
        assert 'version: "latest"' not in workflow
        assert 'version: "0.11.3"' in workflow
        assert "export_requirements.py --check" in workflow
        assert "verify_lambda_bundles.py" in workflow
