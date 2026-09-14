"""Boundary tests for metadata-only queries, without claiming AWS compiler parity.

Pairing and additive billing are tested independently on synthetic returned event
rows in test_memory_cost_reports. The old SQL aggregate emulator is retired: SQL
agreement did not prove either Logs Insights compilation or Lambda retry identity.
"""

import re

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from services.memory_budget import MemoryBudgetPaused
from services.memory_v2._cost_catalog import UnverifiedCost
from services.memory_v2._cost_reports import REPORT_EVENT_LIMIT, report_query

from tests import test_memory_cost_monitor
from tests.test_memory_cost_reports import END, START

budget = test_memory_cost_monitor.budget
SAFE_DISPLAY = {
    "log_group",
    "log_stream",
    "event_ms",
    "event_kind",
    "rid",
    "platform_rid",
    "cost_rid",
    "billed_ms",
    "memory_bytes",
    "cost_schema",
    "memory_request",
    "complete",
    "shared_stats_rru",
    "shared_stats_wru",
    "shared_sqs_units",
    "elapsed_ms",
}


@pytest.mark.parametrize("shared", [False, True])
def test_query_returns_only_closed_event_metadata_without_collapsing_retries(shared):
    query = report_query(START, END, shared=shared)
    commands = [part.strip() for part in query.split("|")]
    displays = [index for index, command in enumerate(commands) if command.startswith("display ")]
    assert len(displays) == 1
    display = displays[0]
    assert all(command.startswith(("limit ", "sort ")) for command in commands[display + 1 :])
    output = [field.strip() for field in commands[display][len("display ") :].split(",")]
    assert len(output) == len(SAFE_DISPLAY) and set(output) == SAFE_DISPLAY
    assert all(not command.startswith(("stats ", "dedup ", "parse ")) for command in commands)
    assert "@message" not in query and "@ptr" not in query
    assert all(kind in query for kind in ("START", "REPORT", "MemoryV2CostStart", "MemoryV2Cost"))
    aliases = re.findall(r"\bas (\w+)", query)
    assert len(aliases) == len(set(aliases))
    # Rows outside core are needed to finish an attempt whose REPORT is in halo;
    # the query must not pre-select only the one earliest timestamp per rid.
    assert "min(" not in query and "max(" not in query


@pytest.mark.parametrize("start,end", [(START, START), (END, START), (START, START + 43201)])
def test_query_rejects_unbounded_or_empty_core_window(start, end):
    with pytest.raises(UnverifiedCost):
        report_query(start, end, shared=False)


def test_actual_botocore_compile_error_retains_real_moto_scan_hold_and_disables_permit(budget):
    service, _, now = test_memory_cost_monitor.monitor(budget)
    telemetry = service.telemetry
    metadata = telemetry.resources()
    start, end = service._blocks(int(now[0]))[0]
    metrics = telemetry.metrics(start, end)
    logs = boto3.client("logs", region_name="eu-central-1")
    telemetry.logs = logs
    with Stubber(logs) as stub:
        stub.add_client_error(
            "start_query",
            service_error_code="MalformedQueryException",
            service_message="Ephemeral field is already defined: platform_starts ([1562,1600])",
            expected_params={
                "logGroupNames": [row["log_group"] for row in service.inventory.functions if row["kind"] == "worker"],
                "startTime": start - 900,
                "endTime": end + 900,
                "queryString": report_query(start, end, shared=False),
                "limit": REPORT_EVENT_LIMIT,
            },
        )
        with pytest.raises(logs.exceptions.MalformedQueryException) as raised:
            telemetry.reports(
                start, end, state=service.state, month=service.state.budget.month(), metadata=metadata, metrics=metrics
            )
        assert isinstance(raised.value, ClientError)
        stub.assert_no_pending_responses()
    state, month = service.state, service.state.budget.month()
    assert state.read(month, "MONITOR")["scan_micro_usd"] == 394
    assert state.read(month, "AWS")["measurement_state"] == "UNVERIFIED"
    with pytest.raises(MemoryBudgetPaused):
        state.budget.reserve("compile-failure-has-no-permit", purpose="extract")


@pytest.mark.parametrize("invocations", [12, 13])
def test_sdk_collector_reconciles_actual_attempts_with_worker_invocation_metrics(budget, invocations):
    from tests.test_memory_cost_reports import invocation, query_result

    service, clients, now = test_memory_cost_monitor.monitor(budget)
    start, end = service._blocks(int(now[0]))[0]
    metadata = service.telemetry.resources()
    metrics = service.telemetry.metrics(start, end)
    group = "/aws/lambda/zerde-serverless-memory-v2-worker-prod"
    rows = []
    for request in range(4):
        for retry in range(3):
            rows += invocation(
                f"retry-request-{request}",
                start_ms=(start + request * 210 + retry * 60 + 1) * 1000,
                group=group,
                billed_ms=(retry + 1) * 1000,
            )
    clients.logs.get_query_results.side_effect = [query_result(rows), query_result([])]
    metrics[("zerde-serverless-memory-v2-worker-prod", "invocations")] = invocations

    def collect():
        return service.telemetry.reports(
            start, end, state=service.state, month=service.state.budget.month(), metadata=metadata, metrics=metrics
        )

    if invocations == 13:
        with pytest.raises(UnverifiedCost):
            collect()
        with pytest.raises(MemoryBudgetPaused):
            service.state.budget.reserve("coverage-gap", purpose="extract")
    else:
        result = collect()
        assert result[group]["reports"] == 12
        assert result[group]["gb_seconds"] == 3
        assert clients.logs.start_query.call_count == 2
        assert all(call.kwargs["limit"] == 10000 for call in clients.logs.start_query.call_args_list)
