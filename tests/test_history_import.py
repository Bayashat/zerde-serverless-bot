"""The retired importer must stop before touching exports or any SDK."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.mark.parametrize("arguments", [[], ["--apply"], ["--export", "/missing/private-export.json"], ["--help"]])
def test_retired_import_rejects_before_files_secrets_or_sdk(arguments, monkeypatch):
    spec = importlib.util.spec_from_file_location("retired_import", "dev/tools/import_telegram_history.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("sys.argv", ["import_telegram_history.py", *arguments])
    with (
        patch("builtins.open", side_effect=AssertionError("no export read")),
        patch.object(Path, "open", side_effect=AssertionError("no export read")),
        patch("boto3.client", side_effect=AssertionError("no SDK")),
        patch("boto3.resource", side_effect=AssertionError("no SDK")),
        patch("boto3.Session", side_effect=AssertionError("no SDK")),
    ):
        with pytest.raises(SystemExit, match="Historical memory import is retired"):
            module.main()
