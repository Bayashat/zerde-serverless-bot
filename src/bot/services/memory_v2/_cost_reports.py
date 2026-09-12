"""Pair bounded, body-free Lambda events into execution attempts, including retries.

AWS reuses RequestId on retries, including in the same log stream. It is not an
invocation identity. A platform START and its following REPORT delimit an attempt.
"""

import re
from collections import defaultdict
from decimal import Decimal

from ._cost_catalog import BLOCK_SECONDS, HALO_SECONDS, UnverifiedCost, number

REPORT_EVENT_LIMIT = 10_000
_KINDS = ("START", "MemoryV2CostStart", "MemoryV2Cost", "REPORT")
_COMMON = {"log_group", "log_stream", "event_ms", "event_kind", "rid"}
_IDENTITY = {"platform_rid", "cost_rid"}
_NUMERIC = {
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
_OUTPUT = ", ".join(
    (
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
    )
)


def report_query(start, end, *, shared):
    if not 0 < end - start <= BLOCK_SECONDS or type(shared) is not bool:
        raise UnverifiedCost("Unbounded REPORT window")
    # Only platform and cost metadata leave Logs Insights. No message text,
    # application payload, prompts or free-form errors are selected.
    return (
        'filter @type in ["START", "REPORT"] or cost_event in ["MemoryV2CostStart", "MemoryV2Cost"]\n'
        "| fields @log as log_group, @logStream as log_stream, toMillis(@timestamp) as event_ms,\n"
        "    coalesce(cost_event, @type) as event_kind,\n"
        "    coalesce(request_id, @requestId) as rid, @requestId as platform_rid, request_id as cost_rid,\n"
        "    @billedDuration as billed_ms, @memorySize as memory_bytes, cost_schema, memory_request, complete,\n"
        "    shared_stats_rru, shared_stats_wru, shared_sqs_units, elapsed_ms\n"
        f"| filter event_ms >= {(start - HALO_SECONDS) * 1000} and event_ms < {(end + HALO_SECONDS) * 1000}\n"
        "| sort event_ms asc\n"
        f"| display {_OUTPUT}\n"
        f"| limit {REPORT_EVENT_LIMIT}"
    )


def _event(items, groups, start, end):
    if not isinstance(items, list):
        raise UnverifiedCost("Invalid REPORT event shape")
    row = {}
    for entry in items:
        if not isinstance(entry, dict) or set(entry) != {"field", "value"}:
            raise UnverifiedCost("Invalid REPORT event shape")
        key, value = entry["field"], entry["value"]
        if key in row:
            raise UnverifiedCost("Duplicate REPORT event fields")
        row[key] = value
    # GetQueryResults automatically adds a pointer even with explicit display.
    # Never persist it, include it in errors, or fetch the referenced log body.
    row.pop("@ptr", None)
    if not _COMMON <= row.keys() or row.keys() - (_COMMON | _IDENTITY | _NUMERIC):
        raise UnverifiedCost("Unexpected or missing REPORT event fields")
    if any(not isinstance(row[key], str) for key in ("log_group", "log_stream", "event_kind", "rid")):
        raise UnverifiedCost("Invalid REPORT event identity")
    group = row["log_group"].split(":", 1)[-1]
    if group not in groups or not isinstance(row["log_stream"], str) or not row["log_stream"]:
        raise UnverifiedCost("REPORT event differs from inventory")
    if row["event_kind"] not in _KINDS or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", row["rid"]):
        raise UnverifiedCost("Invalid REPORT event identity")
    stamp = number(row["event_ms"])
    if stamp != int(stamp) or not (start - HALO_SECONDS) * 1000 <= stamp < (end + HALO_SECONDS) * 1000:
        raise UnverifiedCost("REPORT event is outside the observation window")
    platform = row["event_kind"] in {"START", "REPORT"}
    required_id = "platform_rid" if platform else "cost_rid"
    if row.get(required_id) != row["rid"]:
        raise UnverifiedCost("REPORT event identity fields disagree")
    for key in _IDENTITY:
        if key in row and row[key] not in {"", row["rid"]}:
            raise UnverifiedCost("REPORT event identity fields disagree")
    if platform and row.get("cost_rid"):
        raise UnverifiedCost("Platform event contains a cost identity")
    expected = {
        "START": set(),
        "REPORT": {"billed_ms", "memory_bytes"},
        "MemoryV2CostStart": {"cost_schema", "memory_request"},
        "MemoryV2Cost": {
            "cost_schema",
            "complete",
            "shared_stats_rru",
            "shared_stats_wru",
            "shared_sqs_units",
            "elapsed_ms",
        },
    }[row["event_kind"]]
    present = {key for key in _NUMERIC if key in row and row[key] != ""}
    if present != expected:
        raise UnverifiedCost("Unexpected or missing REPORT event numbers")
    row["log_group"], row["event_ms"] = group, int(stamp)
    return row


def _totals():
    return {
        key: Decimal(0)
        for key in (
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
        )
    }


def parse_reports(result, groups, *, start, end, shared):
    """Strictly account each core-window START; the halo only supplies its tail.

    Missing markers on ordinary shared-Bot calls do not make them V2 calls. Once
    either cost marker exists, the entire attempt must be accounted for. No
    deduplication, count balancing across retries, or maximum-duration shortcut.
    """
    if not 0 < end - start <= BLOCK_SECONDS or type(shared) is not bool:
        raise UnverifiedCost("Unbounded REPORT window")
    rows = result.get("results")
    if result.get("status") != "Complete" or result.get("nextToken") or not isinstance(rows, list):
        raise UnverifiedCost("REPORT query did not finish completely")
    if len(rows) >= REPORT_EVENT_LIMIT or number(result.get("statistics", {}).get("recordsMatched")) != len(rows):
        raise UnverifiedCost("REPORT events are truncated or incomplete")
    streams = defaultdict(list)
    for items in rows:
        event = _event(items, groups, start, end)
        streams[(event["log_group"], event["log_stream"])].append(event)
    parsed = {}
    start_ms, end_ms = start * 1000, end * 1000

    def finish(events):
        kinds = [row["event_kind"] for row in events]
        marked = any(kind in _KINDS[1:3] for kind in kinds)
        if shared and not marked:
            return
        began = events[0]["event_kind"] == "START"
        core = began and start_ms <= events[0]["event_ms"] < end_ms
        touches_core = any(start_ms <= row["event_ms"] < end_ms + 301_000 for row in events)
        if tuple(kinds) != _KINDS:
            if core or touches_core:
                raise UnverifiedCost("START, FINAL or REPORT attempt coverage is incomplete")
            return
        span = events[-1]["event_ms"] - events[0]["event_ms"]
        # Refuse an old START borrowed by a later retry with a missing START.
        # The 1s tolerance accommodates platform log overhead; it is never
        # billed or used to fill missing records. The runtime cap is 300s.
        if span > 301_000 or span > number(events[-1]["billed_ms"]) + 1000:
            raise UnverifiedCost("REPORT attempt timing is inconsistent")
        if not core:
            return
        for row in events:
            for key in _NUMERIC & row.keys():
                if row[key] != "":
                    row[key] = number(row[key])
        if (
            events[1]["cost_schema"] != 1
            or events[2]["cost_schema"] != 1
            or events[1]["memory_request"] != 1
            or events[2]["complete"] != 1
        ):
            raise UnverifiedCost("Cost attempt accounting is incomplete")
        if events[3]["memory_bytes"] <= 0:
            raise UnverifiedCost("REPORT memory size is invalid")
        first, _, final, report = events
        group = first["log_group"]
        values = parsed.setdefault(group, _totals())
        for key in (
            "platform_starts",
            "reports",
            "billed_records",
            "starts",
            "finals",
            "completed",
            "rru_count",
            "wru_count",
            "sqs_count",
        ):
            values[key] += 1
        values["schema_count"] += 2
        values["schema_sum"] += 2
        values["gb_seconds"] += report["billed_ms"] * report["memory_bytes"] / Decimal(1_000_000 * 1024 * 1000)
        values["rru"] += final["shared_stats_rru"]
        values["wru"] += final["shared_stats_wru"]
        values["sqs"] += final["shared_sqs_units"]
        values["elapsed_ms"] += final["elapsed_ms"]

    for events in streams.values():
        at_time = defaultdict(list)
        for event in events:
            at_time[event["event_ms"]].append(event)
        active = []
        for stamp in sorted(at_time):
            by_id = defaultdict(list)
            for event in at_time[stamp]:
                by_id[event["rid"]].append(event)
            # At a same-ms boundary, an already-open different request may
            # close before the next START. Identity makes that order unique.
            order = list(by_id)
            if active and active[0]["rid"] in by_id:
                order.remove(active[0]["rid"])
                order.insert(0, active[0]["rid"])
            elif active:
                if active[0]["event_kind"] == "START":
                    raise UnverifiedCost("Overlapping or unclosed invocation attempts")
                finish(active)
                active = []
            if (
                not active
                and len(by_id) > 1
                and any(row["event_kind"] == "START" for tied in by_id.values() for row in tied)
            ):
                raise UnverifiedCost("Ambiguous invocation boundary without an active start")
            if sum("START" in [x["event_kind"] for x in by_id[rid]] for rid in order) > 1:
                raise UnverifiedCost("Ambiguous simultaneous invocation starts")
            for rid in order:
                tied = by_id[rid]
                kinds = [row["event_kind"] for row in tied]
                if len(kinds) != len(set(kinds)):
                    raise UnverifiedCost("Duplicate or ambiguous REPORT events")
                if active and (active[0]["rid"] != rid or "START" in kinds):
                    if active[0]["rid"] == rid and "START" in kinds and "REPORT" in kinds:
                        raise UnverifiedCost("Ambiguous retry boundary")
                    if active[0]["event_kind"] == "START":
                        raise UnverifiedCost("Overlapping or unclosed invocation attempts")
                    finish(active)
                    active = []
                for event in sorted(tied, key=lambda row: _KINDS.index(row["event_kind"])):
                    active.append(event)
                    if event["event_kind"] == "REPORT":
                        finish(active)
                        active = []
        if active:
            finish(active)
    return parsed
