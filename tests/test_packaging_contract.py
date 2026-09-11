"""Prevent security floors and the checked-in Lambda locks drifting apart."""

import re
import runpy
import tomllib
from pathlib import Path

import pytest


def test_lambda_locks_include_the_complete_matching_sdk_and_hashes():
    locked = {package["name"]: package["version"] for package in tomllib.loads(Path("uv.lock").read_text())["package"]}
    for package in ("bot", "news", "quiz", "operations"):
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


@pytest.mark.parametrize(
    "relative",
    [
        "services/__pycache__/contest.cpython-313.pyc",
        "services/repositories/contest.py",
        "services/handlers/contest.py",
        "services/contest.py",
        "services/handlers/obsolete.pyc",
        "core/nested/obsolete.pyo",
        "__pycache__/main.cpython-313.pyc",
        "main.pyc",
        "main.pyo",
    ],
)
def test_bundle_probe_rejects_first_party_cache_and_retired_module(tmp_path, relative):
    verify = runpy.run_path("scripts/verify_lambda_bundles.py")["verify_first_party_assets"]
    asset = tmp_path / "asset"
    path = asset / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic stale file")
    with pytest.raises(SystemExit, match="(First-party Python cache|Retired contest module)"):
        verify(asset, tmp_path / "layer", "bot")


def test_bundle_probe_checks_shared_layer_but_allows_dependency_cache(tmp_path):
    verify = runpy.run_path("scripts/verify_lambda_bundles.py")["verify_first_party_assets"]
    asset = tmp_path / "asset"
    dependency = asset / "__pycache__/typing_extensions.cpython-313.pyc"
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes(b"dependency compile output")
    verify(asset, tmp_path / "layer", "operations")
    stale = tmp_path / "layer/zerde_common/__pycache__/retired.cpython-313.pyc"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale first-party compile output")
    with pytest.raises(SystemExit, match="First-party Python cache"):
        verify(asset, tmp_path / "layer", "operations")


def test_shared_layer_glob_filter_stages_source_without_local_caches(tmp_path, monkeypatch):
    from aws_cdk import App, Stack

    monkeypatch.syspath_prepend(str(Path("infra").resolve()))
    from components import zerde_layer

    monkeypatch.setattr(zerde_layer, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "src/shared"
    originals = ["python/zerde_common/__init__.py", "python/zerde_common/nested/keep.py"]
    caches = [
        "__pycache__/root.pyc",
        "obsolete.pyc",
        "obsolete.pyo",
        "python/zerde_common/__pycache__/obsolete.cpython-313.pyc",
        "python/zerde_common/nested/obsolete.pyc",
        "python/zerde_common/nested/obsolete.pyo",
    ]
    for name in originals + caches:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic fixture\n")
    outdir = tmp_path / "assembly"
    app = App(outdir=str(outdir))
    zerde_layer.add_zerde_common_layer(Stack(app, "CacheFilter"))
    app.synth()
    assets = [path for path in outdir.glob("asset.*") if path.is_dir()]
    assert len(assets) == 1
    actual = {str(path.relative_to(assets[0])) for path in assets[0].rglob("*") if path.is_file()}
    assert actual == set(originals)
