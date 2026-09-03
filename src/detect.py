"""
RingFence — Detection Engine
==============================
Defense-only collusion / fraud-ring detector.

Approach (deliberately explainable over black-box):
  1. Build a bipartite-derived graph linking entities (merchants + buyers)
     that share infrastructure (device, IP, or payment instrument).
  2. Extract connected clusters -- a cluster is any group of entities
     linked by shared resources.
  3. Score each cluster on four explainable, auditable signals:
       - resource_reuse_score : how tightly the cluster reuses a small
         pool of devices/ips/instruments (low uniqueness = suspicious)
       - velocity_score       : how bursty the cluster's transactions are
         in time (many txns in a short window = suspicious)
       - structuring_score    : how much amounts cluster around round
         numbers (classic structuring / layering signature)
       - refund_score         : refund/chargeback rate inside the cluster
         vs. platform baseline
  4. Combine into a single 0-100 risk score with a documented, tunable
     weighting -- NOT a black box. Every score is traceable to evidence.
  5. Flag clusters above a threshold as "rings requiring review" (NOT
     auto-block -- bounded, gated action per the brief).
  6. Emit a full audit trail: which entities, which shared resources,
     which specific signals fired, and why.

This mirrors intrusion-detection-style graph/anomaly analysis used for
botnet and lateral-movement detection, applied to payments risk.
"""

import json
from collections import defaultdict
from datetime import datetime, timezone

import networkx as nx
import numpy as np
import pandas as pd

from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- Tunable weights (documented, not hidden) -----------------------------
WEIGHTS = {
    "resource_reuse": 0.35,
    "velocity": 0.25,
    "structuring": 0.20,
    "refund": 0.20,
}
RISK_THRESHOLD = 45  # score >= this => flagged for review (bounded action)
# Chosen from tests/sensitivity_sweep.py: on our synthetic test, precision
# stayed a perfect 1.0 for every threshold from 20 to 50 (recall 87%), then
# fell off a cliff at 55+ as it started excluding genuine rings for no
# precision benefit -- every extracted cluster in this dataset was a real
# ring, so 55 was cutting through the middle of the true-ring score
# distribution (51.5-66.5) with no noise population to justify it. 45 keeps
# a safety margin below the observed floor rather than sitting exactly at
# the sweep's technical optimum (20), since real-world traffic will have
# incidental legit clusters this synthetic test can't fully represent.
MIN_CLUSTER_SIZE = 3  # ignore trivial pairs (e.g. one shared household IP)

# A resource (device/IP/instrument) only becomes a graph-linking signal once
# it's been REUSED at least this many times. A single incidental collision
# (e.g. two strangers on the same NAT'd wifi, once) is normal internet noise,
# not fraud -- it's *repeated* reuse across transactions that is the actual
# collusion signature. This threshold is itself an auditable, tunable rule.
MIN_RESOURCE_REUSE = 3  # a resource shared across >=3 distinct entities/txns


def build_graph(df: pd.DataFrame) -> nx.Graph:
    """Entities (merchant_X / buyer_X) become nodes.

    Buyer<->buyer edges come from shared BUYER-owned resources (device,
    IP, payment instrument). Merchant<->merchant edges come from shared
    MERCHANT-owned resources (settlement account, registration IP).
    We deliberately never draw buyer<->merchant edges: a legitimate buyer
    naturally transacts with many different merchants using their own
    device/card, and treating that as a link would flood the graph with
    noise. The actual collusion signature is multiple *different* buyer
    identities (or multiple different merchant identities) covertly
    sharing the same underlying infrastructure -- i.e. one operator
    running several fake accounts on one side of the transaction.

    A resource only becomes a linking signal once it has been reused
    >= MIN_RESOURCE_REUSE times, filtering out one-off incidental overlap
    (e.g. two strangers briefly on the same NAT'd wifi).
    """
    G = nx.Graph()

    buyer_res_counts = defaultdict(int)
    merchant_res_counts = defaultdict(int)
    for res_type, col in [("device", "device_id"), ("ip", "ip_id"), ("instrument", "instrument_id")]:
        for val, cnt in df[col].value_counts().items():
            buyer_res_counts[(res_type, val)] = cnt
    for res_type, col in [("settlement_account", "settlement_account"), ("registration_ip", "registration_ip")]:
        for val, cnt in df[col].value_counts().items():
            merchant_res_counts[(res_type, val)] = cnt

    shared_buyers = defaultdict(set)
    shared_merchants = defaultdict(set)
    for _, row in df.iterrows():
        m_node = f"merchant::{row.merchant_id}"
        b_node = f"buyer::{row.buyer_id}"
        G.add_node(m_node, kind="merchant")
        G.add_node(b_node, kind="buyer")

        for res_type, res_val in [
            ("device", row.device_id), ("ip", row.ip_id), ("instrument", row.instrument_id)
        ]:
            if buyer_res_counts[(res_type, res_val)] >= MIN_RESOURCE_REUSE:
                shared_buyers[(res_type, res_val)].add(b_node)

        for res_type, res_val in [
            ("settlement_account", row.settlement_account),
            ("registration_ip", row.registration_ip),
        ]:
            if merchant_res_counts[(res_type, res_val)] >= MIN_RESOURCE_REUSE:
                shared_merchants[(res_type, res_val)].add(m_node)

    def _link(shared_dict):
        for (res_type, res_val), nodes in shared_dict.items():
            if len(nodes) < 2:
                continue
            nodes = list(nodes)
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    a, b = nodes[i], nodes[j]
                    if G.has_edge(a, b):
                        G[a][b]["evidence"].append((res_type, res_val))
                    else:
                        G.add_edge(a, b, evidence=[(res_type, res_val)])

    _link(shared_buyers)
    _link(shared_merchants)
    return G


def resource_reuse_score(cluster_df: pd.DataFrame) -> float:
    """Lower unique-resource-per-entity ratio => more suspicious reuse.

    IMPORTANT: buyer-owned resources (device/ip/instrument) are only
    compared against the number of BUYERS, and merchant-owned resources
    (settlement account/registration ip) only against the number of
    MERCHANTS. Mixing the two (e.g. dividing buyer-resource counts by
    total entities including merchants) artificially inflates the score
    even for a perfectly clean cluster, since merchants never contribute
    to buyer-side resource pools in the first place.
    """
    n_buyers = cluster_df.buyer_id.nunique()
    n_merchants = cluster_df.merchant_id.nunique()

    buyer_side_scores = []
    if n_buyers > 0:
        n_devices = cluster_df.device_id.nunique()
        n_ips = cluster_df.ip_id.nunique()
        n_instr = cluster_df.instrument_id.nunique()
        avg_unique = np.mean([n_devices, n_ips, n_instr])
        ratio = avg_unique / n_buyers
        buyer_side_scores.append(max(0.0, 1.0 - ratio) * 100)

    merchant_side_scores = []
    if n_merchants > 0:
        n_accts = cluster_df.settlement_account.nunique()
        n_regips = cluster_df.registration_ip.nunique()
        avg_unique_m = np.mean([n_accts, n_regips])
        ratio_m = avg_unique_m / n_merchants
        merchant_side_scores.append(max(0.0, 1.0 - ratio_m) * 100)

    all_scores = buyer_side_scores + merchant_side_scores
    if not all_scores:
        return 0.0
    # Take the max, not the average: a cluster that's clean on the buyer
    # side but tightly sharing settlement accounts on the merchant side is
    # still a real ring -- averaging would dilute a genuine signal.
    return min(max(all_scores), 100)


def velocity_score(cluster_df: pd.DataFrame) -> float:
    """Transactions clustered into a tight time window => burst => risk."""
    ts = pd.to_datetime(cluster_df.timestamp)
    if len(ts) < 2:
        return 0.0
    span_hours = max((ts.max() - ts.min()).total_seconds() / 3600, 0.1)
    txns_per_hour = len(ts) / span_hours
    # squash into 0-100 with a soft cap
    score = min(txns_per_hour * 8, 100)
    return score


def structuring_score(cluster_df: pd.DataFrame) -> float:
    """Detect clustering of amounts around round numbers (classic
    structuring / layering signature to dodge review thresholds)."""
    amounts = cluster_df.amount_inr.values
    if len(amounts) == 0:
        return 0.0
    round_bases = np.array([999, 1999, 4999, 9999, 14999, 49999, 99999])
    closeness = np.array([
        np.min(np.abs(a - round_bases) / round_bases) for a in amounts
    ])
    near_round_frac = np.mean(closeness < 0.03)  # within 3% of a round base
    return near_round_frac * 100


def refund_score(cluster_df: pd.DataFrame, baseline_refund_rate: float) -> float:
    n = len(cluster_df)
    if n == 0:
        return 0.0
    refund_rate = (cluster_df.status == "refunded").mean()
    lift = max(0.0, refund_rate - baseline_refund_rate)
    return min(lift / max(baseline_refund_rate, 0.01) * 25, 100)


def run_detection(txn_path: str) -> dict:
    df = pd.read_csv(txn_path)
    baseline_refund_rate = (df.status == "refunded").mean()

    G = build_graph(df)
    components = [c for c in nx.connected_components(G) if len(c) >= MIN_CLUSTER_SIZE]

    results = []
    audit_log = []

    for idx, comp in enumerate(components):
        merchant_ids = {n.split("::", 1)[1] for n in comp if n.startswith("merchant::")}
        buyer_ids = {n.split("::", 1)[1] for n in comp if n.startswith("buyer::")}

        cluster_df = df[
            df.merchant_id.isin(merchant_ids) | df.buyer_id.isin(buyer_ids)
        ]
        if cluster_df.empty:
            continue

        r_score = resource_reuse_score(cluster_df)
        v_score = velocity_score(cluster_df)
        s_score = structuring_score(cluster_df)
        f_score = refund_score(cluster_df, baseline_refund_rate)

        total = (
            WEIGHTS["resource_reuse"] * r_score
            + WEIGHTS["velocity"] * v_score
            + WEIGHTS["structuring"] * s_score
            + WEIGHTS["refund"] * f_score
        )

        flagged = total >= RISK_THRESHOLD

        # Gather evidence (shared resources) for the audit trail
        evidence_items = []
        subG = G.subgraph(comp)
        for a, b, data in subG.edges(data=True):
            for res_type, res_val in data["evidence"]:
                evidence_items.append(f"{res_type}:{res_val} shared by {a} <-> {b}")
        evidence_items = sorted(set(evidence_items))[:12]  # cap for readability

        cluster_record = {
            "cluster_id": f"cluster_{idx:03d}",
            "n_merchants": len(merchant_ids),
            "n_buyers": len(buyer_ids),
            "n_transactions": len(cluster_df),
            "merchant_ids": sorted(merchant_ids),
            "buyer_ids": sorted(buyer_ids),
            "signals": {
                "resource_reuse_score": round(r_score, 1),
                "velocity_score": round(v_score, 1),
                "structuring_score": round(s_score, 1),
                "refund_score": round(f_score, 1),
            },
            "risk_score": round(total, 1),
            "flagged": bool(flagged),
            "action": "FLAG_FOR_REVIEW" if flagged else "NO_ACTION",
            "txn_ids": cluster_df.txn_id.tolist(),
        }
        results.append(cluster_record)

        audit_log.append({
            "cluster_id": cluster_record["cluster_id"],
            "decision": cluster_record["action"],
            "risk_score": cluster_record["risk_score"],
            "weights_used": WEIGHTS,
            "threshold": RISK_THRESHOLD,
            "signal_breakdown": cluster_record["signals"],
            "evidence": evidence_items,
            "entities_involved": {
                "merchants": sorted(merchant_ids),
                "buyers": sorted(buyer_ids),
            },
            "transaction_count": len(cluster_df),
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        })

    output = {
        "run_meta": {
            "total_transactions": len(df),
            "total_clusters_found": len(results),
            "clusters_flagged": sum(r["flagged"] for r in results),
            "weights": WEIGHTS,
            "threshold": RISK_THRESHOLD,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "clusters": results,
    }

    with open(str(DATA_DIR / "detection_results.json"), "w") as f:
        json.dump(output, f, indent=2)
    with open(str(DATA_DIR / "audit_trail.json"), "w") as f:
        json.dump(audit_log, f, indent=2)

    return output


if __name__ == "__main__":
    out = run_detection(str(DATA_DIR / "transactions.csv"))
    print(f"Clusters found: {out['run_meta']['total_clusters_found']}")
    print(f"Clusters flagged: {out['run_meta']['clusters_flagged']}")
