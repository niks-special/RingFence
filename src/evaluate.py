"""
RingFence — Evaluation
========================
Scores the detector's output against the ground truth that was deliberately
withheld from detect.py. Reports:
  - Transaction-level precision / recall / F1
  - Ring-level (cluster-level) precision / recall -- did we find the actual
    embedded rings, and how many flagged clusters were real rings?
  - False-positive cost estimate -- the operational cost of a wrongly
    flagged legitimate cluster (analyst review time, merchant friction)
    versus the cost of a missed ring (fraud loss), so the risk/reward
    trade-off is explicit and auditable, not just a bare accuracy number.
"""

import json

import pandas as pd

from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# --- Illustrative unit costs (documented assumptions, easily changed) -----
# A false positive costs analyst review time + merchant-relationship friction.
COST_PER_FALSE_POSITIVE_REVIEW_INR = 450     # ~30 min analyst time, loaded cost
COST_PER_FALSE_POSITIVE_FRICTION_INR = 800   # goodwill/support cost if a
                                              # legit merchant cluster is held
# A missed ring (false negative) costs the average fraud volume it would have
# extracted before being caught by a downstream (slower, manual) process.
AVG_MISSED_RING_LOSS_INR = 45000


def main():
    with open(str(DATA_DIR / "detection_results.json")) as f:
        results = json.load(f)
    gt = pd.read_csv(str(DATA_DIR / "ground_truth.csv"))
    gt_txn_map = dict(zip(gt.txn_id, gt.is_ring_gt))
    gt_ring_map = dict(zip(gt.txn_id, gt.ring_id_gt))

    # ---- Transaction-level scoring ----
    predicted_fraud_txns = set()
    for c in results["clusters"]:
        if c["flagged"]:
            predicted_fraud_txns.update(c["txn_ids"])

    all_txn_ids = set(gt.txn_id)
    tp = sum(1 for t in predicted_fraud_txns if gt_txn_map.get(t, False))
    fp = sum(1 for t in predicted_fraud_txns if not gt_txn_map.get(t, False))
    fn = sum(
        1 for t in all_txn_ids
        if gt_txn_map.get(t, False) and t not in predicted_fraud_txns
    )
    tn = len(all_txn_ids) - tp - fp - fn

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # ---- Ring-level (cluster-level) scoring ----
    true_ring_ids = set(gt.ring_id_gt.dropna().unique())
    rings_caught = set()
    flagged_clusters_that_are_real = 0
    flagged_clusters_total = 0
    for c in results["clusters"]:
        if not c["flagged"]:
            continue
        flagged_clusters_total += 1
        ring_ids_in_cluster = {
            gt_ring_map.get(t) for t in c["txn_ids"] if gt_ring_map.get(t)
        }
        if ring_ids_in_cluster:
            flagged_clusters_that_are_real += 1
            rings_caught.update(ring_ids_in_cluster)

    ring_recall = len(rings_caught) / len(true_ring_ids) if true_ring_ids else 0.0
    ring_precision = (
        flagged_clusters_that_are_real / flagged_clusters_total
        if flagged_clusters_total else 0.0
    )

    false_positive_clusters = flagged_clusters_total - flagged_clusters_that_are_real
    missed_rings = len(true_ring_ids) - len(rings_caught)

    fp_cost = false_positive_clusters * (
        COST_PER_FALSE_POSITIVE_REVIEW_INR + COST_PER_FALSE_POSITIVE_FRICTION_INR
    )
    fn_cost = missed_rings * AVG_MISSED_RING_LOSS_INR
    net_value = fn_cost - fp_cost  # rough "money saved by running this system"

    report = {
        "transaction_level": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "ring_level": {
            "true_rings_embedded": len(true_ring_ids),
            "rings_caught": len(rings_caught),
            "rings_caught_ids": sorted(rings_caught),
            "rings_missed_ids": sorted(true_ring_ids - rings_caught),
            "ring_recall": round(ring_recall, 4),
            "flagged_clusters_total": flagged_clusters_total,
            "flagged_clusters_that_were_real_rings": flagged_clusters_that_are_real,
            "ring_precision": round(ring_precision, 4),
            "false_positive_clusters": false_positive_clusters,
        },
        "cost_analysis_inr": {
            "assumptions": {
                "cost_per_false_positive_review": COST_PER_FALSE_POSITIVE_REVIEW_INR,
                "cost_per_false_positive_friction": COST_PER_FALSE_POSITIVE_FRICTION_INR,
                "avg_missed_ring_loss": AVG_MISSED_RING_LOSS_INR,
            },
            "total_false_positive_cost": fp_cost,
            "total_missed_ring_cost": fn_cost,
            "net_value_of_running_detector": net_value,
        },
    }

    with open(str(DATA_DIR / "evaluation_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
