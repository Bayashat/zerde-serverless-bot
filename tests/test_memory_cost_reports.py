"""Synthetic event evidence for per-execution billing; no AWS/compiler claim.

Fixtures describe independent START-to-REPORT executions, including Lambda
retries that reuse awsRequestId. Expected totals add each billed REPORT, never
infer them from request-id cardinality or equal global marker counts.
"""

from copy import deepcopy
from decimal import Decimal
from random import Random

import pytest
from services.memory_v2._cost_catalog import UnverifiedCost
from services.memory_v2._cost_reports import REPORT_EVENT_LIMIT, parse_reports

START, END = 1789146000, 1789146900
GROUP = "/aws/lambda/zerde-serverless-memory-v2-worker-prod"
STREAM = "2026/09/11/[$LATEST]synthetic-stream"


def invocation(rid="synthetic-request", *, start_ms=None, group=GROUP, stream=STREAM, billed_ms=1000):
    start_ms = (START + 1) * 1000 if start_ms is None else start_ms
    common = {"log_group": group, "log_stream": stream, "rid": rid}
    return [
        {**common, "event_ms": start_ms, "event_kind": "START", "platform_rid": rid},
        {
            **common,
            "event_ms": start_ms,
            "event_kind": "MemoryV2CostStart",
            "cost_rid": rid,
            "cost_schema": 1,
            "memory_request": 1,
        },
        {
            **common,
            "event_ms": start_ms + 1000,
            "event_kind": "MemoryV2Cost",
            "cost_rid": rid,
            "cost_schema": 1,
            "complete": 1,
            "elapsed_ms": 50,
            "shared_stats_rru": 10,
            "shared_stats_wru": 20,
            "shared_sqs_units": 3,
        },
        {
            **common,
            "event_ms": start_ms + 2000,
            "event_kind": "REPORT",
            "platform_rid": rid,
            "billed_ms": billed_ms,
            "memory_bytes": 128000000,
        },
    ]


def query_result(rows, **changes):
    return {
        "status": "Complete",
        "results": [[{"field": key, "value": str(value)} for key, value in row.items()] for row in rows],
        "statistics": {"recordsMatched": len(rows), "bytesScanned": 0},
        **changes,
    }


def parsed(rows, *, start=START, end=END, shared=False, groups=(GROUP,)):
    return parse_reports(query_result(rows), list(groups), start=start, end=end, shared=shared)


@pytest.mark.parametrize("shared", [False, True])
def test_four_reused_request_ids_each_have_three_separately_billed_attempts(shared):
    rows = []
    # Four requests in one warm stream. Each has retries at +60 and +180s;
    # differing durations ensure max(duration) cannot masquerade as a sum.
    for request in range(4):
        for retry, delay in enumerate((0, 60, 180), start=1):
            rows += invocation(
                f"request-{request}",
                start_ms=(START + request * 210 + delay + 1) * 1000,
                billed_ms=retry * 1000,
            )
    Random(31).shuffle(rows)
    values = parsed(rows, shared=shared)[GROUP]
    assert values["platform_starts"] == values["reports"] == values["starts"] == values["finals"] == 12
    assert values["gb_seconds"] == Decimal("3")
    assert values["rru"] == 120 and values["wru"] == 240 and values["sqs"] == 36
    assert values["elapsed_ms"] == 600
    assert values["invalid_records"] == 0


def test_same_request_id_in_distinct_streams_is_not_deduplicated():
    rows = invocation() + invocation(stream=STREAM + "-other", billed_ms=3000)
    values = parsed(rows)[GROUP]
    assert values["reports"] == 2 and values["gb_seconds"] == Decimal("0.5")


@pytest.mark.parametrize("shared", [False, True])
def test_core_boundary_assigns_each_retry_by_its_own_platform_start(shared):
    rows = (
        invocation(start_ms=(START - 1) * 1000, billed_ms=7000)
        + invocation(start_ms=(START + 60) * 1000, billed_ms=1000)
        + invocation(start_ms=(END - 1) * 1000, billed_ms=3000)
        + invocation(start_ms=(END + 60) * 1000, billed_ms=9000)
    )
    values = parsed(rows, shared=shared)[GROUP]
    assert values["reports"] == values["starts"] == 2
    assert values["gb_seconds"] == Decimal("0.5")


def test_adjacent_core_windows_do_not_double_bill_a_retry():
    boundary = START + 120
    rows = invocation(start_ms=(boundary - 1) * 1000) + invocation(start_ms=boundary * 1000 + 60000)
    before = parsed(rows, end=boundary)[GROUP]
    after = parsed(rows, start=boundary)[GROUP]
    assert before["reports"] == after["reports"] == 1
    assert before["gb_seconds"] + after["gb_seconds"] == Decimal("0.25")


@pytest.mark.parametrize("event_index", [0, 1, 2, 3])
def test_wrong_event_identity_cannot_be_borrowed_from_another_attempt(event_index):
    rows = invocation()
    rows[event_index]["rid"] = "wrong-request"
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize(
    "event_index, identity", [(0, "platform_rid"), (1, "cost_rid"), (2, "cost_rid"), (3, "platform_rid")]
)
def test_coalesced_id_must_agree_with_the_event_specific_identity(event_index, identity):
    rows = invocation()
    rows[event_index][identity] = "other-request"
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("shared", [False, True])
def test_duplicate_and_missing_final_cannot_cancel_between_retries(shared):
    first, second = invocation(), invocation(start_ms=(START + 61) * 1000)
    first.append(deepcopy(first[2]))
    second.pop(2)
    rows = first + second
    assert sum(row["event_kind"] == "MemoryV2Cost" for row in rows) == 2
    with pytest.raises(UnverifiedCost):
        parsed(rows, shared=shared)


@pytest.mark.parametrize("removed", [0, 1, 2, 3])
def test_each_required_event_must_exist_for_a_core_worker_attempt(removed):
    rows = invocation()
    rows.pop(removed)
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("duplicate", [0, 1, 2, 3])
def test_duplicate_event_is_not_silently_deduplicated(duplicate):
    rows = invocation()
    rows.append(deepcopy(rows[duplicate]))
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_same_millisecond_within_one_attempt_has_unambiguous_event_roles():
    rows = invocation()
    rows[2]["event_ms"] = rows[3]["event_ms"]
    assert parsed(list(reversed(rows)))[GROUP]["reports"] == 1


def test_same_millisecond_previous_report_and_next_start_is_ambiguous():
    first = invocation()
    second = invocation(start_ms=first[3]["event_ms"])
    with pytest.raises(UnverifiedCost):
        parsed(first + second)


def test_cost_final_after_next_attempt_starts_cannot_fill_the_previous_gap():
    first = invocation()
    second = invocation(start_ms=(START + 61) * 1000)
    first[2]["event_ms"] = second[1]["event_ms"] + 1
    with pytest.raises(UnverifiedCost):
        parsed(first + second)


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "incomplete",
        "missing_rru",
        "negative_wru",
        "negative_sqs",
        "negative_elapsed",
        "negative_billed",
        "missing_memory",
        "zero_memory",
        "boolean_counter",
        "nonfinite",
    ],
)
def test_invalid_numeric_or_schema_evidence_is_not_accepted(fault):
    rows = invocation()
    if fault == "schema":
        rows[2]["cost_schema"] = 2
    elif fault == "incomplete":
        rows[2]["complete"] = 0
    elif fault == "missing_rru":
        rows[2].pop("shared_stats_rru")
    elif fault == "missing_memory":
        rows[3].pop("memory_bytes")
    else:
        target, field, value = {
            "negative_wru": (2, "shared_stats_wru", -1),
            "negative_sqs": (2, "shared_sqs_units", -1),
            "negative_elapsed": (2, "elapsed_ms", -1),
            "negative_billed": (3, "billed_ms", -1),
            "zero_memory": (3, "memory_bytes", 0),
            "boolean_counter": (2, "shared_stats_rru", True),
            "nonfinite": (2, "shared_stats_rru", "NaN"),
        }[fault]
        rows[target][field] = value
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("field", ["@message", "private_payload", "unexpected_aggregate"])
def test_unknown_result_fields_are_rejected(field):
    rows = invocation()
    rows[2][field] = "synthetic-private-content"
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_duplicate_wire_field_is_rejected_before_it_can_overwrite_identity():
    result = query_result(invocation())
    result["results"][0].append({"field": "rid", "value": "overwritten"})
    with pytest.raises(UnverifiedCost):
        parse_reports(result, [GROUP], start=START, end=END, shared=False)


@pytest.mark.parametrize(
    "fault",
    [
        "next_token",
        "missing_statistics",
        "missing_records_matched",
        "truncated",
        "extra_rows",
        "fractional_count",
        "negative_count",
        "not_complete",
    ],
)
def test_query_completion_proves_the_whole_event_set_was_returned(fault):
    result = query_result(invocation())
    if fault == "next_token":
        result["nextToken"] = "not-complete"
    elif fault == "missing_statistics":
        result.pop("statistics")
    elif fault == "missing_records_matched":
        result["statistics"].pop("recordsMatched")
    elif fault == "not_complete":
        result["status"] = "Running"
    else:
        result["statistics"]["recordsMatched"] = {
            "truncated": 5,
            "extra_rows": 3,
            "fractional_count": 4.5,
            "negative_count": -1,
        }[fault]
    with pytest.raises(UnverifiedCost):
        parse_reports(result, [GROUP], start=START, end=END, shared=False)


@pytest.mark.parametrize("count", [10000, 10001])
def test_result_at_or_over_the_event_limit_cannot_authorize_usage(count):
    assert REPORT_EVENT_LIMIT == 10000
    rows = [
        event for index in range((count + 3) // 4) for event in invocation(f"request-{index}", stream=f"stream-{index}")
    ][:count]
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_complete_empty_result_is_valid_only_with_explicit_zero_matched():
    assert parsed([]) == {}


def test_shared_bot_excludes_a_complete_ordinary_attempt_but_not_its_v2_retry():
    ordinary = [row for row in invocation() if row["event_kind"] in {"START", "REPORT"}]
    rows = ordinary + invocation(start_ms=(START + 61) * 1000, billed_ms=3000)
    value = parsed(rows, shared=True)[GROUP]
    assert value["reports"] == value["starts"] == 1 and value["gb_seconds"] == Decimal("0.375")
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("orphan", [1, 2])
def test_shared_orphan_memory_marker_is_not_classified_as_ordinary(orphan):
    with pytest.raises(UnverifiedCost):
        parsed([invocation()[orphan]], shared=True)


def test_wrong_log_group_cannot_supply_report_evidence():
    with pytest.raises(UnverifiedCost):
        parsed(invocation(group=GROUP + "-unregistered"))


def test_service_added_pointer_is_ignored_and_never_returned():
    rows = invocation()
    for row in rows:
        row["@ptr"] = "opaque-service-pointer-not-for-storage"
    result = parsed(rows)
    assert result[GROUP]["reports"] == 1
    assert "opaque-service-pointer" not in str(result)


@pytest.mark.parametrize("field", ["log_group", "log_stream", "event_ms", "event_kind", "rid"])
def test_required_common_event_metadata_cannot_be_omitted(field):
    rows = invocation()
    rows[1].pop(field)
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("kind_index", [0, 3])
def test_platform_event_cannot_be_reclassified_by_a_cost_identity(kind_index):
    rows = invocation()
    rows[kind_index]["cost_rid"] = rows[kind_index]["rid"]
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_platform_id_discovered_on_custom_log_must_match_the_custom_id():
    rows = invocation()
    for event in rows[1:3]:
        event["platform_rid"] = event["rid"]
    assert parsed(rows)[GROUP]["reports"] == 1
    rows[2]["platform_rid"] = "foreign-invocation"
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_one_attempt_can_have_all_four_distinct_events_in_the_same_millisecond():
    rows = invocation(billed_ms=1)
    for event in rows:
        event["event_ms"] = rows[0]["event_ms"]
    assert parsed(list(reversed(rows)))[GROUP]["reports"] == 1


@pytest.mark.parametrize(
    "event_index,identity", [(0, "platform_rid"), (1, "cost_rid"), (2, "cost_rid"), (3, "platform_rid")]
)
def test_event_specific_identity_is_required(event_index, identity):
    rows = invocation()
    rows[event_index].pop(identity)
    with pytest.raises(UnverifiedCost):
        parsed(rows)


def test_memory_marker_from_previous_retry_cannot_cover_next_retry():
    first = invocation()
    second = invocation(start_ms=(START + 61) * 1000)
    first.append(deepcopy(first[1]))
    second.pop(1)
    with pytest.raises(UnverifiedCost):
        parsed(first + second)


@pytest.mark.parametrize("remaining", [(3,), (2, 3)])
def test_determinably_prior_core_halo_fragments_do_not_invent_an_in_core_attempt(remaining):
    prior = invocation(start_ms=(START - 10) * 1000)
    rows = [prior[index] for index in remaining] + invocation(start_ms=(START + 1) * 1000)
    assert parsed(rows)[GROUP]["reports"] == 1


def test_core_orphan_report_is_not_dismissed_as_a_prior_core_fragment():
    with pytest.raises(UnverifiedCost):
        parsed([invocation()[3]])


def test_service_log_account_prefix_normalizes_only_to_registered_group():
    result = parsed(invocation(group="123456789012:" + GROUP))
    assert set(result) == {GROUP}
    assert result[GROUP]["reports"] == 1


@pytest.mark.parametrize("stamp", [(START - 901) * 1000, (END + 900) * 1000, "NaN", "1.5", True])
def test_event_time_cannot_escape_or_obscure_the_fixed_halo(stamp):
    rows = invocation()
    rows[2]["event_ms"] = stamp
    with pytest.raises(UnverifiedCost):
        parsed(rows)


@pytest.mark.parametrize("rid", ["", "contains whitespace", "a" * 129])
def test_request_identity_must_be_bounded_opaque_metadata(rid):
    with pytest.raises(UnverifiedCost):
        parsed(invocation(rid))


def test_public_totals_keep_only_the_fixed_numeric_cost_consumer_contract():
    expected = {
        "invalid_records": 0,
        "platform_starts": 1,
        "reports": 1,
        "billed_records": 1,
        "gb_seconds": Decimal("0.125"),
        "starts": 1,
        "finals": 1,
        "completed": 1,
        "schema_count": 2,
        "schema_sum": 2,
        "rru_count": 1,
        "rru": 10,
        "wru_count": 1,
        "wru": 20,
        "sqs_count": 1,
        "sqs": 3,
        "elapsed_ms": 50,
    }
    assert parsed(invocation()) == {GROUP: expected}


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("side", ["before", "after"])
@pytest.mark.parametrize("fault", ["incomplete", "schema", "negative_cost"])
def test_definite_out_of_core_attempt_failure_does_not_poison_healthy_core(shared, side, fault):
    outside_start = (START - 60 if side == "before" else END + 60) * 1000
    outside = invocation("outside", start_ms=outside_start)
    if fault == "incomplete":
        outside[2]["complete"] = 0
    elif fault == "schema":
        outside[1]["cost_schema"] = outside[2]["cost_schema"] = 2
    else:
        outside[2]["shared_stats_wru"] = -10
    core = invocation("healthy-core", billed_ms=3000)
    value = parsed(outside + core, shared=shared)[GROUP]
    assert value["reports"] == value["starts"] == 1
    assert value["gb_seconds"] == Decimal("0.375")
    assert value["wru"] == 20


@pytest.mark.parametrize("shared", [False, True])
def test_different_request_ids_cannot_overlap_in_one_lambda_log_stream(shared):
    first = invocation("first")
    overlapping = invocation("second", start_ms=first[0]["event_ms"] + 500)
    with pytest.raises(UnverifiedCost):
        parsed(first + overlapping, shared=shared)


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("final_tied", [False, True])
def test_different_request_ids_identify_a_valid_same_millisecond_attempt_boundary(shared, final_tied):
    first = invocation("first", billed_ms=1000)
    if final_tied:
        first[2]["event_ms"] = first[3]["event_ms"]
    second = invocation("second", start_ms=first[3]["event_ms"], billed_ms=3000)
    values = parsed(list(reversed(first + second)), shared=shared)[GROUP]
    assert values["reports"] == 2
    assert values["gb_seconds"] == Decimal("0.5")
    assert values["wru"] == 40


@pytest.mark.parametrize("shared", [False, True])
def test_previous_halo_start_cannot_hide_a_core_retry_missing_its_start(shared):
    old_start = invocation(start_ms=(START - 60) * 1000)[0]
    retry = invocation(start_ms=(START + 1) * 1000, billed_ms=1000)
    # This superficially supplies four event kinds under the same request id,
    # but 63 seconds of platform elapsed time cannot belong to a 1 second bill.
    with pytest.raises(UnverifiedCost):
        parsed([old_start] + retry[1:], shared=shared)


@pytest.mark.parametrize("shared", [False, True])
def test_unclosed_prior_halo_attempt_with_core_markers_is_not_silently_ignored(shared):
    old_start = invocation(start_ms=(START - 60) * 1000)[0]
    retry = invocation(start_ms=(START + 1) * 1000)
    with pytest.raises(UnverifiedCost):
        parsed([old_start] + retry[1:3], shared=shared)


def test_shared_ordinary_attempt_cannot_wrap_an_overlapping_memory_attempt():
    ordinary = invocation("ordinary", billed_ms=3000)
    ordinary[3]["event_ms"] = ordinary[0]["event_ms"] + 4000
    ordinary = [row for row in ordinary if row["event_kind"] in {"START", "REPORT"}]
    memory = invocation("memory", start_ms=ordinary[0]["event_ms"] + 500)
    # Dropping ordinary open START and then its delayed orphan REPORT would
    # accept an impossible overlapping execution in one Lambda log stream.
    with pytest.raises(UnverifiedCost):
        parsed(ordinary + memory, shared=True)


def test_shared_ordinary_attempt_can_close_before_next_memory_start_at_same_millisecond():
    ordinary = [row for row in invocation("ordinary") if row["event_kind"] in {"START", "REPORT"}]
    memory = invocation("memory", start_ms=ordinary[-1]["event_ms"])
    assert parsed(ordinary + memory, shared=True)[GROUP]["reports"] == 1
