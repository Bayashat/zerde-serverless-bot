"""Recovery diagnostics use fixed labels without changing retry/continuation."""

import io
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import memory_worker_main as entry
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from services.memory_v2.lifecycle import MemoryLifecycle, MemoryPurgeRecoveryError
from services.memory_v2.recovery import MemoryRecoveryError
from zerde_common.logger import JSONFormatter, ZerdeLoggerAdapter

SECRET = "unconfigured-private-message-source-ref-token-123"


@pytest.fixture
def recovery(monkeypatch):
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JSONFormatter())
    logger = logging.Logger("worker-recovery-test", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(entry, "logger", ZerdeLoggerAdapter(logger, {}))
    # Exercise the real entrypoint. Only its unrelated metering decorator is
    # inactive without inventory; all recovery dependencies are local fakes.
    monkeypatch.delenv("MEMORY_COST_INVENTORY", raising=False)
    repo = object()
    monkeypatch.setattr(entry, "get_memory_ingestion", lambda: SimpleNamespace(repo=repo))
    calls = []
    failures = {}

    def operation(stage):
        def run(*args, **kwargs):
            calls.append((stage, kwargs))
            if stage in failures:
                raise failures[stage]
            return {"synthetic_count": 1}

        return run

    monkeypatch.setattr(MemoryLifecycle, "recover", operation("purges"))
    monkeypatch.setattr(entry.MemoryRecovery, "run", operation("ingestion"))
    monkeypatch.setattr(entry, "maintain_trends", operation("trends"))
    return failures, calls, output


@pytest.mark.parametrize(
    ("stage", "error", "expected"),
    [
        ("purges", MemoryPurgeRecoveryError(SECRET), {"error_type": "MemoryPurgeRecoveryError"}),
        ("ingestion", MemoryRecoveryError(SECRET), {"error_type": "MemoryRecoveryError"}),
        (
            "trends",
            EndpointConnectionError(endpoint_url="https://private.invalid/" + SECRET),
            {"error_type": "EndpointConnectionError"},
        ),
        ("purges", type(SECRET, (RuntimeError,), {})(SECRET), {"error_type": "UnexpectedError"}),
        (
            "ingestion",
            ClientError({"Error": {"Code": "AccessDeniedException", "Message": SECRET}, "RequestId": SECRET}, SECRET),
            {"error_type": "ClientError", "aws_error_code": "AccessDeniedException"},
        ),
        (
            "trends",
            ClientError({"Error": {"Code": SECRET, "Message": SECRET}}, SECRET),
            {"error_type": "ClientError", "aws_error_code": "OtherAwsError"},
        ),
    ],
)
def test_failure_logs_only_fixed_stage_type_and_approved_aws_code(recovery, stage, error, expected):
    failures, calls, output = recovery
    failures[stage] = error
    # A chained exception and traceback must never enter the emitted JSON.
    error.__cause__ = RuntimeError("source-body-" + SECRET)
    with pytest.raises(RuntimeError, match="^Durable memory recovery remains pending$"):
        entry.lambda_handler({"schema": 2, "task_type": "RECOVER_MEMORY_V2"}, None)
    assert [name for name, _ in calls] == ["purges", "ingestion", "trends"]
    assert calls[0][1] == {"max_pages": 2, "runtime_seconds": 20}
    assert calls[1][1] == {"max_pages": 4}
    assert calls[2][1]["runtime_seconds"] == 15
    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    assert SECRET not in lines[0] and "Traceback" not in lines[0]
    fields = json.loads(lines[0])
    assert set(fields) == {"level", "message", "timestamp", "location", "stage", *expected}
    assert fields["message"] == "Memory recovery stage remains pending"
    assert fields["stage"] == stage
    assert all(fields[key] == value for key, value in expected.items())


def test_all_failed_stages_are_attempted_and_logged_before_same_aggregate_retry(recovery):
    failures, calls, output = recovery
    failures.update({stage: RuntimeError(SECRET) for stage in ("purges", "ingestion", "trends")})
    with pytest.raises(RuntimeError, match="^Durable memory recovery remains pending$"):
        entry.lambda_handler({"schema": 2, "task_type": "RECOVER_MEMORY_V2"}, None)
    assert [name for name, _ in calls] == ["purges", "ingestion", "trends"]
    assert [json.loads(line)["stage"] for line in output.getvalue().splitlines()] == ["purges", "ingestion", "trends"]
    assert SECRET not in output.getvalue()


def test_success_results_and_silent_logging_remain_unchanged(recovery):
    _, calls, output = recovery
    assert entry.lambda_handler({"schema": 2, "task_type": "RECOVER_MEMORY_V2"}, None) == {
        stage: {"synthetic_count": 1} for stage in ("purges", "ingestion", "trends")
    }
    assert [name for name, _ in calls] == ["purges", "ingestion", "trends"]
    assert output.getvalue() == ""


def test_missing_configuration_preserves_existing_failure_without_inventing_a_stage(recovery, monkeypatch):
    _, calls, output = recovery
    monkeypatch.setattr(entry, "get_memory_ingestion", lambda: None)
    with pytest.raises(RuntimeError, match="^Memory V2 recovery is not configured$"):
        entry.lambda_handler({"schema": 2, "task_type": "RECOVER_MEMORY_V2"}, None)
    assert calls == [] and output.getvalue() == ""


def test_event_payload_is_not_logged_or_treated_as_recovery(recovery, monkeypatch):
    _, calls, output = recovery
    repo = Mock(side_effect=AssertionError("unsupported event must not create a repository"))
    monkeypatch.setattr(entry, "get_memory_v2_repo", repo)
    with pytest.raises(ValueError, match="^Unsupported Memory V2 event$"):
        entry.lambda_handler({"schema": 2, "task_type": "RECOVER_MEMORY_V2", "payload": SECRET}, None)
    repo.assert_not_called()
    assert calls == [] and output.getvalue() == ""
