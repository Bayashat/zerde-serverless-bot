"""Body-free, per-wire-attempt attribution of shared AWS work inside V2 spans.

Model charges and dedicated V2 resources have different owners. Missing hook or
inventory evidence makes this meter UNVERIFIED, never a fabricated zero bill.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
import weakref
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import partial

from zerde_common.logger import get_json_logger

_SCHEMA = 1
_LOG_LIMIT = 64 * 1024
_STATE_KEY = "memory_v2_cost_call"
_SCOPE = ContextVar("memory_v2_cost_scope", default=None)
_CALLS = ContextVar("memory_v2_cost_calls", default=())
_CLIENTS = weakref.WeakKeyDictionary()
_REGISTRY_LOCK = threading.RLock()
_REGISTRATION_FAILED = False
_DDB_CC_OPERATIONS = {
    "GetItem",
    "PutItem",
    "UpdateItem",
    "DeleteItem",
    "Query",
    "Scan",
    "BatchGetItem",
    "BatchWriteItem",
    "TransactGetItems",
    "TransactWriteItems",
}


@dataclass(frozen=True)
class CostInventory:
    shared_stats_table: str
    shared_main_queue_url: str
    excluded_tables: frozenset[str]
    excluded_queue_urls: frozenset[str]
    version: str
    factory_coverage_verified: bool = False
    shared_stats_index_count: int | None = None
    shared_stats_replica_count: int | None = None
    main_queue_max_receive_count: int = 3
    max_sqs_message_bytes: int = 1_048_576
    required_hook_services: frozenset[str] = frozenset({"dynamodb", "sqs"})

    def verified(self):
        return (
            isinstance(self.shared_stats_table, str)
            and bool(self.shared_stats_table)
            and isinstance(self.shared_main_queue_url, str)
            and self.shared_main_queue_url.startswith("https://")
            and isinstance(self.version, str)
            and bool(self.version)
            and self.factory_coverage_verified is True
            and type(self.shared_stats_index_count) is int
            and self.shared_stats_index_count == 0
            and type(self.shared_stats_replica_count) is int
            and self.shared_stats_replica_count == 0
            and type(self.main_queue_max_receive_count) is int
            and self.main_queue_max_receive_count == 3
            and type(self.max_sqs_message_bytes) is int
            and self.max_sqs_message_bytes == 1_048_576
            and self.shared_stats_table not in self.excluded_tables
            and self.shared_main_queue_url not in self.excluded_queue_urls
            and self.required_hook_services == frozenset({"dynamodb", "sqs"})
        )


@dataclass
class _Quote:
    rru: float = 0
    wru: float = 0
    sqs: float = 0
    complete: bool = True
    shared_tables: frozenset[str] = frozenset()


@dataclass
class _Call:
    meter: InvocationCostMeter
    service: str
    operation: str
    client_id: int
    attempts: int = 0
    last: _Quote | None = None
    finished: bool = False


def _number(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Ambiguous SDK request shape")
        result[key] = value
    return result


def _default_emit(fields):
    # The shared formatter exposes _extra fields at the outer JSON level.
    get_json_logger(__name__, "INFO").info("Memory V2 cost observation", extra={"_extra": fields})


class InvocationCostMeter:
    def __init__(self, context, inventory: CostInventory, *, emit=_default_emit, clock=time.monotonic):
        request_id = getattr(context, "aws_request_id", None)
        self.request_id = (
            request_id if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9-]{8,128}", request_id) else ""
        )
        self.inventory, self.emit, self.clock = inventory, emit, clock
        self.started_at = None
        self.closed = False
        self.complete = bool(self.request_id) and inventory.verified()
        self.rru = self.wru = self.sqs = 0.0
        self.pending = self.spans = 0
        self.log_bytes = 0
        self._lock = threading.RLock()

    def _emit(self, fields):
        size = len(json.dumps(fields, separators=(",", ":"), ensure_ascii=False).encode()) + 512
        self.log_bytes += size
        if self.log_bytes > _LOG_LIMIT:
            self.complete = False
            if "complete" in fields:
                fields["complete"] = 0
        try:
            self.emit(fields)
        except Exception:
            # Do not replace or leak a business exception through diagnostics.
            # Missing Start/Final is separately detected by the REPORT collector.
            self.complete = False

    def touch(self):
        with self._lock:
            if self.closed:
                self.complete = False
                return False
            if self.started_at is None:
                self.started_at = self.clock()
                self._emit(
                    {
                        "cost_event": "MemoryV2CostStart",
                        "cost_schema": _SCHEMA,
                        "request_id": self.request_id,
                        "memory_request": 1,
                    }
                )
            return True

    @contextmanager
    def bind_invocation(self):
        """Install a lazy owner in the outer context before async/thread copies.

        No Start is emitted until touch(). Enter and reset always occur in this
        same calling context; activation is shared mutable invocation state.
        """
        previous = _SCOPE.get()
        if previous is not None and previous is not self:
            previous.complete = self.complete = False
        token = _SCOPE.set(self)
        try:
            yield self
        finally:
            _SCOPE.reset(token)

    @contextmanager
    def span(self):
        active = self.touch()
        if active:
            with self._lock:
                self.spans += 1
        previous = _SCOPE.get()
        if previous is not None and previous is not self:
            previous.complete = self.complete = False
        token = _SCOPE.set(self if active else None)
        try:
            yield self
        finally:
            _SCOPE.reset(token)
            if active:
                with self._lock:
                    self.spans -= 1

    def mark_incomplete(self):
        with self._lock:
            self.complete = False

    def finish(self):
        """Invoke once from the Lambda outer finally, after all V2 tasks finish."""
        with self._lock:
            if self.closed:
                return
            self.closed = True
            if self.started_at is None:
                return
            with _REGISTRY_LOCK:
                installed = set(_CLIENTS.values())
                hooks_ok = not _REGISTRATION_FAILED and self.inventory.required_hook_services <= installed
            elapsed = (self.clock() - self.started_at) * 1000
            valid_elapsed = _number(elapsed)
            self.complete = self.complete and hooks_ok and self.pending == 0 and self.spans == 0 and valid_elapsed
            self._emit(
                {
                    "cost_event": "MemoryV2Cost",
                    "cost_schema": _SCHEMA,
                    "request_id": self.request_id,
                    "complete": int(self.complete),
                    "elapsed_ms": math.ceil(elapsed) if valid_elapsed else 0,
                    "shared_stats_rru": self.rru,
                    "shared_stats_wru": self.wru,
                    "shared_sqs_units": self.sqs,
                }
            )


def _table_scope(name, inventory):
    if name == inventory.shared_stats_table:
        return "shared"
    if isinstance(name, str) and name in inventory.excluded_tables:
        return "excluded"
    return "unknown"


def _ddb_quote(operation, body, inventory):
    q = _Quote()
    entries = []
    if operation in {"DescribeTable", "DescribeContinuousBackups"}:
        # The cost monitor owns these metadata API reservations for its exact
        # dedicated-table roster. Other control-plane calls remain unknown.
        return _Quote(complete=_table_scope(body.get("TableName"), inventory) == "excluded")
    if operation in {"GetItem", "Query", "Scan", "PutItem", "UpdateItem", "DeleteItem"}:
        read = 256 if operation in {"Query", "Scan"} else 100
        entries = [(body.get("TableName"), read, 400 if operation in {"PutItem", "UpdateItem", "DeleteItem"} else 0)]
    elif operation in {"BatchGetItem", "BatchWriteItem"}:
        requests = body.get("RequestItems")
        if not isinstance(requests, dict) or not requests:
            return _Quote(complete=False)
        total = 0
        for table, requests_for_table in requests.items():
            rows = (
                requests_for_table.get("Keys")
                if operation == "BatchGetItem" and isinstance(requests_for_table, dict)
                else requests_for_table
            )
            if not isinstance(rows, list) or not rows:
                return _Quote(complete=False)
            total += len(rows)
            # Factor two deliberately overbounds nontransactional batch work.
            entries.append((table, 200 * len(rows), 800 * len(rows) if operation == "BatchWriteItem" else 0))
        if total > (100 if operation == "BatchGetItem" else 25):
            q.complete = False
    elif operation in {"TransactGetItems", "TransactWriteItems"}:
        rows = body.get("TransactItems")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
            return _Quote(complete=False)
        allowed = {"Get"} if operation == "TransactGetItems" else {"ConditionCheck", "Put", "Update", "Delete"}
        for row in rows:
            if not isinstance(row, dict) or len(row) != 1 or not set(row) <= allowed:
                return _Quote(complete=False)
            name, item = next(iter(row.items()))
            if not isinstance(item, dict):
                return _Quote(complete=False)
            entries.append((item.get("TableName"), 200, 800 if name in {"Put", "Update", "Delete"} else 0))
    else:
        return _Quote(complete=False)
    tables = set()
    for table, read, write in entries:
        scope = _table_scope(table, inventory)
        if scope == "shared":
            q.rru += read
            q.wru += write
            tables.add(table)
        elif scope == "unknown":
            q.complete = False
    q.shared_tables = frozenset(tables)
    if body.get("IndexName") and _table_scope(body.get("TableName"), inventory) == "shared":
        q.complete = False  # Current approved shared stats inventory has no index.
    return q


def _sqs_quote(operation, body, inventory):
    url = body.get("QueueUrl")
    if isinstance(url, str) and url in inventory.excluded_queue_urls:
        return _Quote()
    if url != inventory.shared_main_queue_url:
        return _Quote(complete=False)
    if operation == "SendMessage":
        message = body.get("MessageBody")
        valid = isinstance(message, str) and len(message.encode()) <= inventory.max_sqs_message_bytes
        return _Quote(sqs=115, complete=valid)
    if operation == "SendMessageBatch":
        entries = body.get("Entries")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 10:
            return _Quote(complete=False)
        valid = all(isinstance(row, dict) and isinstance(row.get("MessageBody"), str) for row in entries)
        if valid:
            valid = sum(len(row["MessageBody"].encode()) for row in entries) <= inventory.max_sqs_message_bytes
        # 16 units send + 3 * (16 receive + 1 delete + 16 DLQ), per message,
        # even for an uncertain send. Batch send itself is intentionally overcounted.
        return _Quote(sqs=115 * len(entries), complete=valid)
    if operation == "ReceiveMessage":
        count = body.get("MaxNumberOfMessages", 1)
        return (
            _Quote(sqs=16 * count, complete=True) if type(count) is int and 1 <= count <= 10 else _Quote(complete=False)
        )
    if operation in {"DeleteMessage", "ChangeMessageVisibility", "GetQueueAttributes"}:
        return _Quote(sqs=1)
    if operation in {"DeleteMessageBatch", "ChangeMessageVisibilityBatch"}:
        entries = body.get("Entries")
        return (
            _Quote(sqs=len(entries))
            if isinstance(entries, list) and 1 <= len(entries) <= 10
            else _Quote(complete=False)
        )
    return _Quote(complete=False)


def _wire_quote(service, operation, request, inventory):
    try:
        # Never persist request data, table names, URLs, headers or exceptions.
        raw = request.body
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        body = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(body, dict):
            return _Quote(complete=False)
        if service == "dynamodb":
            return _ddb_quote(operation, body, inventory)
        if service == "sqs":
            return _sqs_quote(operation, body, inventory)
    except (AttributeError, ValueError, TypeError, OverflowError):
        pass
    return _Quote(complete=False)


def _before_parameters(params, model, **kwargs):
    meter = _SCOPE.get()
    if meter is not None and meter.started_at is not None and not meter.closed and model.name in _DDB_CC_OPERATIONS:
        # TOTAL includes table/index consumption; do not downgrade explicit INDEXES.
        if params.get("ReturnConsumedCapacity") in {None, "NONE"}:
            params["ReturnConsumedCapacity"] = "TOTAL"


def _before_call(model, context, *, service, client_id, **kwargs):
    meter = _SCOPE.get()
    if meter is None or meter.started_at is None or meter.closed:
        return
    state = _Call(meter, service, model.name, client_id)
    context[_STATE_KEY] = state
    _CALLS.set((*_CALLS.get(), state))
    with meter._lock:
        meter.pending += 1


def _before_send(request, event_name, *, service, client_id, **kwargs):
    meter = _SCOPE.get()
    if meter is None or meter.started_at is None:
        return
    stack = _CALLS.get()
    operation = event_name.rsplit(".", 1)[-1]
    state = stack[-1] if stack else None
    if (
        meter.closed
        or state is None
        or state.meter is not meter
        or state.client_id != client_id
        or state.operation != operation
    ):
        meter.mark_incomplete()
        return
    quote = _wire_quote(service, operation, request, meter.inventory)
    with meter._lock:
        meter.rru += quote.rru
        meter.wru += quote.wru
        meter.sqs += quote.sqs
        meter.complete = meter.complete and quote.complete
        state.attempts += 1
        state.last = quote


def _consumed(parsed, tables):
    capacities = parsed.get("ConsumedCapacity")
    if isinstance(capacities, dict):
        capacities = [capacities]
    if not isinstance(capacities, list):
        return None
    seen, read, write = set(), 0.0, 0.0
    for row in capacities:
        if not isinstance(row, dict) or row.get("TableName") in seen:
            return None
        name = row.get("TableName")
        seen.add(name)
        if name not in tables:
            continue
        # Both fields are required: an aggregate CapacityUnits value does not
        # identify reads versus writes in a mixed transaction.
        if not _number(row.get("ReadCapacityUnits")) or not _number(row.get("WriteCapacityUnits")):
            return None
        read += row["ReadCapacityUnits"]
        write += row["WriteCapacityUnits"]
    return (read, write) if tables <= seen else None


def _finish_call(context, *, http_response=None, parsed=None, **kwargs):
    state = context.get(_STATE_KEY)
    if not isinstance(state, _Call) or state.finished:
        return
    meter = state.meter
    with meter._lock:
        if state.attempts == 0 or meter.closed:
            meter.complete = False
        if (
            state.last
            and state.last.shared_tables
            and getattr(http_response, "status_code", 500) < 300
            and isinstance(parsed, dict)
        ):
            consumed = _consumed(parsed, state.last.shared_tables)
            if consumed is not None:
                read, write = consumed
                meter.rru += read - state.last.rru
                meter.wru += write - state.last.wru
        state.finished = True
        meter.pending -= 1
    stack = _CALLS.get()
    if not stack or stack[-1] is not state:
        meter.mark_incomplete()
    _CALLS.set(tuple(call for call in stack if call is not state))


def register_client(client):
    """Install hooks on each real client at the shared factory; never make calls."""
    global _REGISTRATION_FAILED
    with _REGISTRY_LOCK:
        try:
            if client in _CLIENTS:
                return True
            service = client.meta.service_model.service_id.hyphenize()
            events = client.meta.events
            handlers = {
                f"before-call.{service}": partial(_before_call, service=service, client_id=id(client)),
                f"before-send.{service}": partial(_before_send, service=service, client_id=id(client)),
                f"after-call.{service}": _finish_call,
                f"after-call-error.{service}": _finish_call,
            }
            if service == "dynamodb":
                handlers[f"before-parameter-build.{service}"] = _before_parameters
            for name, handler in handlers.items():
                events.register(name, handler, unique_id=f"memory-v2-cost:{name}")
            _CLIENTS[client] = service
            return True
        except Exception:
            _REGISTRATION_FAILED = True
            meter = _SCOPE.get()
            if meter is not None:
                meter.mark_incomplete()
            return False
