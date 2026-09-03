"""
Unit tests for RingFence's core scoring functions and graph builder.

Each test isolates ONE signal on a hand-built tiny dataframe with a known
correct answer -- so if resource_reuse_score is broken, this test suite
tells you exactly that, instead of a vague "recall dropped" from an
end-to-end run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd
import pytest

from detect import (
    resource_reuse_score,
    velocity_score,
    structuring_score,
    refund_score,
    build_graph,
    MIN_RESOURCE_REUSE,
)


def _base_row(**overrides):
    row = dict(
        txn_id="t", merchant_id="m1", buyer_id="b1",
        device_id="d1", ip_id="ip1", instrument_id="pi1",
        settlement_account="acct1", registration_ip="regip1",
        amount_inr=500.0, status="success",
        timestamp="2026-06-01T10:00:00",
    )
    row.update(overrides)
    return row


# ---------------------------------------------------------------- resource_reuse
def test_resource_reuse_high_when_few_resources_many_entities():
    """20 buyers, all funnelled through 1 device/ip/instrument -> should be
    near-maximum suspicion."""
    rows = [
        _base_row(buyer_id=f"b{i}", merchant_id=f"m{i}",
                   device_id="shared_dev", ip_id="shared_ip", instrument_id="shared_pi",
                   settlement_account=f"acct{i}", registration_ip=f"regip{i}")
        for i in range(20)
    ]
    df = pd.DataFrame(rows)
    score = resource_reuse_score(df)
    assert score > 80, f"expected high reuse score, got {score}"


def test_resource_reuse_low_when_everyone_has_own_resources():
    """5 buyers AND 5 merchants each with their OWN unique resources on
    both sides -> should look clean."""
    rows = [
        _base_row(buyer_id=f"b{i}", merchant_id=f"m{i}",
                   device_id=f"dev{i}", ip_id=f"ip{i}", instrument_id=f"pi{i}",
                   settlement_account=f"acct{i}", registration_ip=f"regip{i}")
        for i in range(5)
    ]
    df = pd.DataFrame(rows)
    score = resource_reuse_score(df)
    assert score < 20, f"expected low reuse score, got {score}"


# ---------------------------------------------------------------- velocity
def test_velocity_high_for_burst():
    """20 transactions inside a single hour -> high burst score."""
    rows = [
        _base_row(txn_id=f"t{i}", timestamp=f"2026-06-01T10:{i%59:02d}:00")
        for i in range(20)
    ]
    df = pd.DataFrame(rows)
    score = velocity_score(df)
    assert score > 50, f"expected high velocity score for a burst, got {score}"


def test_velocity_low_when_spread_over_weeks():
    """Same 20 transactions but spread across 20 different days -> low score."""
    rows = [
        _base_row(txn_id=f"t{i}", timestamp=f"2026-06-{(i%28)+1:02d}T10:00:00")
        for i in range(20)
    ]
    df = pd.DataFrame(rows)
    score = velocity_score(df)
    assert score < 15, f"expected low velocity score when spread out, got {score}"


# ---------------------------------------------------------------- structuring
def test_structuring_high_for_round_amounts():
    rows = [_base_row(txn_id=f"t{i}", amount_inr=amt) for i, amt in
            enumerate([999, 1999, 4999, 9999, 14999] * 3)]
    df = pd.DataFrame(rows)
    score = structuring_score(df)
    assert score > 90, f"expected near-100 structuring score, got {score}"


def test_structuring_low_for_natural_amounts():
    rows = [_base_row(txn_id=f"t{i}", amount_inr=amt) for i, amt in
            enumerate([137.50, 2843.12, 615.00, 91.25, 3320.75])]
    df = pd.DataFrame(rows)
    score = structuring_score(df)
    assert score < 20, f"expected low structuring score for natural amounts, got {score}"


# ---------------------------------------------------------------- refund
def test_refund_score_zero_at_baseline():
    rows = [_base_row(txn_id=f"t{i}", status="success") for i in range(20)]
    df = pd.DataFrame(rows)
    score = refund_score(df, baseline_refund_rate=0.04)
    assert score == 0.0


def test_refund_score_high_when_elevated():
    rows = (
        [_base_row(txn_id=f"t{i}", status="refunded") for i in range(6)]
        + [_base_row(txn_id=f"t{i+6}", status="success") for i in range(4)]
    )
    df = pd.DataFrame(rows)
    score = refund_score(df, baseline_refund_rate=0.04)
    assert score > 50, f"expected high refund-lift score, got {score}"


# ---------------------------------------------------------------- build_graph
def test_graph_links_buyers_sharing_reused_device():
    """3 different buyers repeatedly sharing one device (>=3 uses) should
    become a connected component."""
    rows = [
        _base_row(txn_id=f"t{i}", buyer_id=b, merchant_id=f"m{i}", device_id="dev_shared")
        for i, b in enumerate(["bA", "bB", "bC"] * 2)  # 6 txns, dev reused 6x
    ]
    df = pd.DataFrame(rows)
    G = build_graph(df)
    assert G.has_edge("buyer::bA", "buyer::bB")
    assert G.has_edge("buyer::bB", "buyer::bC")


def test_graph_ignores_one_off_incidental_collision():
    """A device reused only twice (below MIN_RESOURCE_REUSE) should NOT
    create a link -- that's the whole point of the reuse threshold."""
    assert MIN_RESOURCE_REUSE >= 3, "test assumes threshold of >=3"
    rows = [
        _base_row(txn_id="t0", buyer_id="bA", device_id="dev_once"),
        _base_row(txn_id="t1", buyer_id="bB", device_id="dev_once"),  # used 2x only
    ]
    df = pd.DataFrame(rows)
    G = build_graph(df)
    assert not G.has_edge("buyer::bA", "buyer::bB"), (
        "a resource used only twice should not create a link"
    )


def test_graph_never_links_buyer_to_merchant():
    """Core design invariant: buyer<->merchant edges must never exist, no
    matter how much resource sharing there is, because a buyer legitimately
    transacts with many merchants using their own device."""
    rows = [
        _base_row(txn_id=f"t{i}", buyer_id="b_loyal", merchant_id=f"m{i}", device_id="dev_b_loyal")
        for i in range(10)  # one buyer, ten different merchants, same device
    ]
    df = pd.DataFrame(rows)
    G = build_graph(df)
    for i in range(10):
        assert not G.has_edge("buyer::b_loyal", f"merchant::m{i}")


def test_graph_links_merchants_sharing_settlement_account():
    rows = [
        _base_row(txn_id=f"t{i}", merchant_id=m, buyer_id=f"b{i}", settlement_account="acct_shared")
        for i, m in enumerate(["mA", "mB", "mC"] * 2)
    ]
    df = pd.DataFrame(rows)
    G = build_graph(df)
    assert G.has_edge("merchant::mA", "merchant::mB")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
