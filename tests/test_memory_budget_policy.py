"""Policy changes preserve liabilities and require a real, fresh AWS observation."""

from unittest.mock import Mock, patch

import pytest
from services.memory_budget import MONTHLY_LIMIT_MICRO_USD, RESERVATION_MICRO_USD, MemoryBudgetPaused
from services.memory_v2._cost_state import AWS_LIMIT, AWS_STOP, BUDGET_POLICY, CostState, CostStateConflict

from tests import test_memory_budget

budget = test_memory_budget.budget


def legacy(repo, *, amount=2_875_970, paused=True):
    key = repo._key(repo.month(), "AWS")
    row = repo.table.get_item(Key=key, ConsistentRead=True)["Item"]
    row.pop("budget_policy")
    row.pop("stop_micro_usd")
    row.update(budget_micro_usd=3_000_000, estimate_micro_usd=amount, base_estimate_micro_usd=amount, paused=paused)
    repo.table.put_item(Item=row)
    return row


def measure(repo, now, *, amount=0, verified=True, covered=None):
    return CostState(repo, clock=lambda: now[0]).record_measurement(
        repo.month(),
        inventory_version=repo.inventory_version,
        verified=verified,
        estimate=amount,
        covered_until=int(now[0]) if covered is None else covered,
        reason="SYNTHETIC_COMPLETE",
    )


def test_known_old_threshold_migrates_without_refunding_unknown_reservation(budget):
    repo, now = budget
    repo.reserve("unknown-old-call", purpose="extract")
    model_before = repo.snapshot()
    old = legacy(repo)
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()
    row = measure(repo, now)
    assert row["budget_policy"] == BUDGET_POLICY and row["budget_micro_usd"] == AWS_LIMIT
    assert row["stop_micro_usd"] == AWS_STOP and row["paused"] is False
    assert row["estimate_micro_usd"] == old["estimate_micro_usd"]
    state = CostState(repo)
    history = state.read(repo.month(), f"POLICY_HISTORY#AWS#{old['revision']}")
    assert history["previous"] == old
    assert repo.snapshot() == model_before
    repo.check_available()
    measure(repo, now)
    assert state.read(repo.month(), f"POLICY_HISTORY#AWS#{old['revision']}") == history


@pytest.mark.parametrize(
    "mutation", ["low_paused", "high_unpaused", "unknown_policy", "wrong_limit", "boolean_revision"]
)
def test_unknown_pause_cannot_be_laundered_by_an_incomplete_cost_increase(budget, mutation):
    repo, now = budget
    old = legacy(repo)
    changes = {
        "low_paused": {"estimate_micro_usd": 100, "base_estimate_micro_usd": 100},
        "high_unpaused": {"paused": False},
        "unknown_policy": {"budget_policy": "unknown"},
        "wrong_limit": {"budget_micro_usd": 4_000_000},
        "boolean_revision": {"revision": True},
    }
    old.update(changes[mutation])
    repo.table.put_item(Item=old)
    for verified in (False, True):
        with pytest.raises(CostStateConflict):
            measure(repo, now, amount=10_000_000, verified=verified)
        assert repo.table.get_item(Key=repo._key(repo.month(), "AWS"))["Item"] == old
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()


@pytest.mark.parametrize("cause", ["unverified", "stale_coverage", "future_coverage", "scan_bound"])
def test_migration_waits_for_complete_fresh_unambiguous_observation(budget, cause):
    repo, now = budget
    legacy(repo)
    if cause == "scan_bound":
        repo.table.put_item(
            Item={
                **repo._key(repo.month(), "MONITOR"),
                "revision": 1,
                "scan_micro_usd": 500,
                "scan_bound_exceeded": True,
            }
        )
    covered = int(now[0]) + (1 if cause == "future_coverage" else -10800 if cause == "stale_coverage" else 0)
    row = measure(repo, now, verified=cause != "unverified", covered=covered)
    assert "budget_policy" not in row and row["budget_micro_usd"] == 3_000_000
    assert row["paused"] and row["measurement_state"] == "UNVERIFIED"
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()


def test_model_accounting_pause_survives_aws_policy_migration(budget):
    repo, now = budget
    control = {"pk": "MEMORY_BUDGET#CONTROL", "sk": "MODEL", "paused": True}
    repo.table.put_item(Item=control)
    legacy(repo)
    assert measure(repo, now)["paused"] is False
    assert repo.table.get_item(Key={"pk": control["pk"], "sk": "MODEL"})["Item"] == control
    with pytest.raises(MemoryBudgetPaused):
        repo.check_available()


def test_cas_race_does_not_commit_migration_or_audit(budget):
    repo, now = budget
    old = legacy(repo)
    transaction = repo.table.meta.client.transact_write_items

    def race(**kwargs):
        repo.table.put_item(Item={**old, "revision": old["revision"] + 1})
        return transaction(**kwargs)

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=race):
        with pytest.raises(CostStateConflict):
            measure(repo, now)
    state = CostState(repo)
    assert "budget_policy" not in state.read(repo.month(), "AWS")
    assert not state.read(repo.month(), f"POLICY_HISTORY#AWS#{old['revision']}")


def test_commit_ack_loss_is_resolved_by_state_not_a_second_migration(budget):
    repo, now = budget
    old = legacy(repo)
    transaction = repo.table.meta.client.transact_write_items

    def lost_ack(**kwargs):
        transaction(**kwargs)
        raise TimeoutError("synthetic lost acknowledgement")

    with patch.object(repo.table.meta.client, "transact_write_items", side_effect=lost_ack):
        with pytest.raises(TimeoutError):
            measure(repo, now)
    state = CostState(repo)
    history = state.read(repo.month(), f"POLICY_HISTORY#AWS#{old['revision']}")
    assert history and state.read(repo.month(), "AWS")["budget_policy"] == BUDGET_POLICY
    measure(repo, now)
    assert state.read(repo.month(), f"POLICY_HISTORY#AWS#{old['revision']}") == history


def test_superseded_pending_notice_preserves_event_then_allows_new_eighty_percent(budget):
    repo, now = budget
    measure(repo, now, amount=AWS_STOP)
    state = CostState(repo, clock=lambda: now[0])
    notice = state.read(repo.month(), "NOTICE#AWS")
    notice.pop("budget_policy")
    notice.pop("budget_micro_usd")
    repo.table.put_item(Item=notice)
    legacy(repo)
    now[0] += 1
    measure(repo, now)
    superseded = state.read(repo.month(), "NOTICE#AWS")
    assert superseded["state"] == "SUPERSEDED" and superseded["event"] == notice["event"]
    assert superseded["revision"] > notice["revision"]
    assert state.read(repo.month(), f"POLICY_HISTORY#NOTICE#AWS#{notice['revision']}")["previous"] == notice
    sns = Mock()
    assert state.dispatch_notices(sns=sns, topic_arn="test") == 0
    sns.publish.assert_not_called()
    now[0] += 1
    measure(repo, now, amount=24_000_000)
    current = state.read(repo.month(), "NOTICE#AWS")
    assert current["event"]["threshold_percent"] == 80 and current["event"]["status"] == "warning"
    assert current["event"]["observed_at"] != notice["event"]["observed_at"]
    assert current["revision"] > superseded["revision"]


@pytest.mark.parametrize(
    "amount,paused,threshold",
    [
        (23_999_999, False, None),
        (24_000_000, False, 80),
        (26_999_999, False, 80),
        (27_000_000, True, 90),
        (30_000_000, True, 100),
    ],
)
def test_new_aws_policy_boundaries(budget, amount, paused, threshold):
    repo, now = budget
    assert measure(repo, now, amount=amount)["paused"] is paused
    notice = CostState(repo).read(repo.month(), "NOTICE#AWS")
    assert notice.get("event", {}).get("threshold_percent") == threshold
    if paused:
        assert measure(repo, now, amount=0)["paused"] is True


@pytest.mark.parametrize("extra,allowed", [(0, True), (1, False)])
def test_last_full_model_reservation_boundary(budget, extra, allowed):
    repo, _ = budget
    charged = MONTHLY_LIMIT_MICRO_USD - RESERVATION_MICRO_USD + extra
    repo.table.put_item(Item={**repo._key(repo.month(), "MODEL"), "charged_micro_usd": charged})
    if allowed:
        repo.reserve("last-room", purpose="extract")
        assert repo.snapshot()["charged_micro_usd"] == MONTHLY_LIMIT_MICRO_USD
        with pytest.raises(MemoryBudgetPaused):
            repo.reserve("second-room", purpose="answer")
    else:
        with pytest.raises(MemoryBudgetPaused):
            repo.reserve("no-room", purpose="extract")
        assert repo.snapshot()["charged_micro_usd"] == charged


def test_bad_current_policy_amount_is_not_repaired_into_a_permit(budget):
    repo, now = budget
    state = CostState(repo)
    row = state.read(repo.month(), "AWS")
    row["estimate_micro_usd"] = -1
    repo.table.put_item(Item=row)
    with pytest.raises(CostStateConflict):
        measure(repo, now)
    assert state.read(repo.month(), "AWS") == row


def test_legacy_notice_marker_mismatch_aborts_whole_migration(budget):
    repo, now = budget
    measure(repo, now, amount=AWS_STOP)
    state = CostState(repo)
    notice = state.read(repo.month(), "NOTICE#AWS")
    notice.pop("budget_policy")
    notice.pop("budget_micro_usd")
    repo.table.put_item(Item=notice)
    original = legacy(repo)
    key = {"pk": "MEMORY_BUDGET#NOTICE_OUTBOX", "sk": repo.month() + "#AWS"}
    marker = repo.table.get_item(Key=key)["Item"]
    repo.table.put_item(Item={**marker, "revision": marker["revision"] + 1})
    with pytest.raises(CostStateConflict):
        measure(repo, now, amount=24_000_000)
    assert state.read(repo.month(), "AWS") == original
    assert state.read(repo.month(), "NOTICE#AWS") == notice
    assert not state.read(repo.month(), f"POLICY_HISTORY#AWS#{original['revision']}")
