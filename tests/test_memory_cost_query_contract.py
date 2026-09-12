"""Query dataflow and aggregate semantics, without claiming AWS compiler parity.

A small SQLite translation evaluates the existing two-stage numeric expressions
on synthetic invocation rows. It does not implement or replace Logs Insights.
"""

import hashlib
import re
import sqlite3
from copy import deepcopy
from decimal import Decimal

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from services.memory_budget import MemoryBudgetPaused
from services.memory_v2._cost_catalog import UnverifiedCost, parse_reports, report_query

from tests import test_memory_cost_monitor

budget = test_memory_cost_monitor.budget
START, END = 1789146000, 1789146900
GROUP = "/aws/lambda/zerde-serverless-memory-v2-worker-prod"
FIELDS = {
    "invalid_records",
    "platform_starts",
    "reports",
    "billed_records",
    "gb_seconds",
    "starts",
    "finals",
    "completed",
    "schema_count",
    "schema_sum",
    "rru_count",
    "rru",
    "wru_count",
    "wru",
    "sqs_count",
    "sqs",
    "elapsed_ms",
}
RAW_FIELDS = [
    "@log",
    "@timestamp",
    "@type",
    "@requestId",
    "@billedDuration",
    "@memorySize",
    "request_id",
    "cost_event",
    "cost_schema",
    "memory_request",
    "complete",
    "shared_stats_rru",
    "shared_stats_wru",
    "shared_sqs_units",
    "elapsed_ms",
]


def invocation(request_id="synthetic-one", *, start=START + 1, group=GROUP):
    common = {"@log": group, "@timestamp": start * 1000}
    return [
        {**common, "@type": "START", "@requestId": request_id},
        {**common, "cost_event": "MemoryV2CostStart", "request_id": request_id, "cost_schema": 1, "memory_request": 1},
        {
            **common,
            "@timestamp": (start + 1) * 1000,
            "cost_event": "MemoryV2Cost",
            "request_id": request_id,
            "cost_schema": 1,
            "complete": 1,
            "elapsed_ms": 50,
            "shared_stats_rru": 10,
            "shared_stats_wru": 20,
            "shared_sqs_units": 3,
        },
        {
            **common,
            "@timestamp": (start + 2) * 1000,
            "@type": "REPORT",
            "@requestId": request_id,
            "@billedDuration": 1000,
            "@memorySize": 128000000,
        },
    ]


def sql_expression(expression):
    expression = re.sub(r'"([^"\n]*)"', lambda match: "'" + match[1] + "'", expression)
    expression = re.sub(r"@[A-Za-z]+", lambda match: '"' + match[0] + '"', expression)
    expression = re.sub(r"\bif\(", "iif(", expression)
    return expression.replace("[", "(").replace("]", ")")


def evaluate(query, rows):
    """Execute actual query expressions; resolve aliases through SQL CTEs."""
    with sqlite3.connect(":memory:") as database:
        database.row_factory = sqlite3.Row
        database.create_function("ispresent", 1, lambda value: value is not None)
        database.create_function("toMillis", 1, lambda value: value)
        string_fields = {"@log", "@type", "@requestId", "request_id", "cost_event"}
        columns = ", ".join('"' + field + '" ' + ("TEXT" if field in string_fields else "REAL") for field in RAW_FIELDS)
        database.execute(f"CREATE TABLE events ({columns})")
        database.executemany(
            "INSERT INTO events VALUES (" + ",".join("?" for _ in RAW_FIELDS) + ")",
            [[row.get(field) for field in RAW_FIELDS] for row in rows],
        )
        previous, statements = "events", []
        for index, command in enumerate(query.split("|")):
            kind, expression = command.strip().split(maxsplit=1)
            expression = sql_expression(expression)
            if kind == "fields":
                select = f"SELECT *, {expression} FROM {previous}"
            elif kind == "filter":
                select = f"SELECT * FROM {previous} WHERE {expression}"
            else:
                assert kind == "stats"
                aggregate, groups = re.split(r"\bby\b", expression)
                select = f"SELECT {aggregate}, {groups} FROM {previous} GROUP BY {groups}"
            previous = f"stage_{index}"
            statements.append(f"{previous} AS ({select})")
        result = database.execute("WITH " + ",".join(statements) + " SELECT * FROM " + previous)
        return [dict(row) for row in result]


def parsed(rows):
    return parse_reports(
        {
            "status": "Complete",
            "results": [[{"field": key, "value": str(value)} for key, value in row.items()] for row in rows],
        },
        [GROUP],
    )


@pytest.mark.parametrize("shared", [False, True])
def test_aliases_are_single_assignment_and_final_public_schema_stays_exact(shared):
    query = report_query(START, END, shared=shared)
    # The fixed live query is changed only by intermediate names, preserving all
    # predicates, weights, grouping keys and public field names byte-for-byte.
    original = re.sub(r"\breq_", "", query)
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "d32aaa4dcee39e3addb69b3430f2ab29db688c34e88a1f675ec9547ff38ab7a4"
        if shared
        else "e9b9b3084e00e20856868163207245a5c20b5ccc9f5c2b3e5baf45b293f8d548"
    )
    aliases = re.findall(r"\bas (\w+)", query)
    assert len(set(aliases)) == len(aliases)
    stats = [part.strip() for part in query.split("|") if part.strip().startswith("stats ")]
    assert len(stats) == 2
    assert set(re.findall(r"\bas (\w+)", stats[-1])) == FIELDS
    # A missing renamed reference fails evaluation rather than silently yielding
    # the expected literal query string. Every public total is consumer-validated.
    result = evaluate(query, invocation() + invocation("synthetic-two", start=END - 1))
    assert len(result) == 1 and set(result[0]) == FIELDS | {"@log"}
    values = parsed(result)[GROUP]
    assert values == {
        "invalid_records": 0,
        "platform_starts": 2,
        "reports": 2,
        "billed_records": 2,
        "gb_seconds": Decimal("0.25"),
        "starts": 2,
        "finals": 2,
        "completed": 2,
        "schema_count": 4,
        "schema_sum": 4,
        "rru_count": 2,
        "rru": 20,
        "wru_count": 2,
        "wru": 40,
        "sqs_count": 2,
        "sqs": 6,
        "elapsed_ms": 100,
    }


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize(
    "fault",
    [
        "missing_platform_start",
        "missing_final",
        "missing_report",
        "duplicate_start",
        "duplicate_report",
        "schema_version",
        "incomplete",
        "missing_rru",
        "negative_wru",
        "negative_sqs",
        "negative_elapsed",
        "missing_id",
    ],
)
def test_each_invocation_still_fails_closed_for_incomplete_or_invalid_metering(shared, fault):
    rows = invocation()
    if fault == "missing_platform_start":
        rows.pop(0)
    elif fault == "missing_final":
        rows.pop(2)
    elif fault == "missing_report":
        rows.pop(3)
    elif fault == "duplicate_start":
        rows.append(deepcopy(rows[1]))
    elif fault == "duplicate_report":
        rows.append(deepcopy(rows[3]))
    elif fault == "schema_version":
        rows[2]["cost_schema"] = 2
    elif fault == "incomplete":
        rows[2]["complete"] = 0
    elif fault == "missing_rru":
        rows[2].pop("shared_stats_rru")
    elif fault == "negative_wru":
        rows[2]["shared_stats_wru"] = -1
    elif fault == "negative_sqs":
        rows[2]["shared_sqs_units"] = -1
    elif fault == "negative_elapsed":
        rows[2]["elapsed_ms"] = -1
    else:
        for row in rows:
            row.pop("request_id", None)
            row.pop("@requestId", None)
    result = evaluate(report_query(START, END, shared=shared), rows)
    assert result[0]["invalid_records"] == 1
    with pytest.raises(UnverifiedCost):
        parsed(result)


@pytest.mark.parametrize("shared", [False, True])
def test_window_uses_original_start_even_when_final_and_report_cross_end(shared):
    rows = invocation("before", start=START - 1) + invocation("inside", start=END - 1) + invocation("after", start=END)
    values = parsed(evaluate(report_query(START, END, shared=shared), rows))[GROUP]
    assert values["starts"] == values["reports"] == 1
    assert values["gb_seconds"] == Decimal("0.125")


def test_shared_bot_excludes_untouched_invocation_but_worker_requires_instrumentation():
    untouched = [row for row in invocation("untouched") if "@type" in row]
    rows = invocation() + untouched
    assert parsed(evaluate(report_query(START, END, shared=True), rows))[GROUP]["starts"] == 1
    worker = evaluate(report_query(START, END, shared=False), rows)
    assert worker[0]["invalid_records"] == 1
    with pytest.raises(UnverifiedCost):
        parsed(worker)


def test_equal_global_totals_cannot_hide_one_duplicate_and_one_missing_final():
    first, second = invocation("duplicate"), invocation("missing")
    first.append(deepcopy(first[2]))
    second.pop(2)
    result = evaluate(report_query(START, END, shared=True), first + second)
    assert result[0]["starts"] == result[0]["finals"] == 2
    assert result[0]["invalid_records"] == 2
    with pytest.raises(UnverifiedCost):
        parsed(result)


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
                "limit": 100,
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
