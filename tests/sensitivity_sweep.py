"""
RingFence — Threshold Sensitivity Analysis
=============================================
Instead of eyeballing RISK_THRESHOLD, sweep it across a range and measure
precision/recall/F1 at each point -- then pick the threshold that maximizes
F1 (or whatever the operator actually cares about; F1 is a reasonable
default when false positives and false negatives are both costly, which
the cost analysis in evaluate.py suggests they are here).

Also sweeps MIN_RESOURCE_REUSE (the graph-linking threshold) since that's
the other main tunable knob, and it interacts with RISK_THRESHOLD.

Honest caveat: this sweep is tuned on the SAME synthetic dataset used for
the headline metrics, which is a real limitation -- in production this
should be done on a separate validation split, not the test set being
reported on. That trade-off is deliberately called out in the notebook.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json
import importlib

import pandas as pd
import matplotlib.pyplot as plt

import detect as detect_module

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TESTS_DIR = Path(__file__).resolve().parent


def score_at(threshold, min_reuse):
    """Re-run detection with a given threshold/min_reuse and score it."""
    detect_module.RISK_THRESHOLD = threshold
    detect_module.MIN_RESOURCE_REUSE = min_reuse
    results = detect_module.run_detection(str(DATA_DIR / "transactions.csv"))

    gt = pd.read_csv(DATA_DIR / "ground_truth.csv")
    gt_map = dict(zip(gt.txn_id, gt.is_ring_gt))

    predicted = set()
    for c in results["clusters"]:
        if c["flagged"]:
            predicted.update(c["txn_ids"])

    all_ids = set(gt.txn_id)
    tp = sum(1 for t in predicted if gt_map.get(t, False))
    fp = sum(1 for t in predicted if not gt_map.get(t, False))
    fn = sum(1 for t in all_ids if gt_map.get(t, False) and t not in predicted)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"threshold": threshold, "min_reuse": min_reuse,
            "precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn}


def main():
    thresholds = list(range(20, 85, 5))
    reuse_values = [2, 3, 4]

    all_rows = []
    for reuse in reuse_values:
        for th in thresholds:
            row = score_at(th, reuse)
            all_rows.append(row)
            print(f"reuse={reuse}  threshold={th:3d}  "
                  f"P={row['precision']:.3f}  R={row['recall']:.3f}  F1={row['f1']:.3f}")

    df = pd.DataFrame(all_rows)
    df.to_csv(TESTS_DIR / "sensitivity_results.csv", index=False)

    # Plot precision/recall/F1 vs threshold, one line set per reuse value
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
    metrics = ["precision", "recall", "f1"]
    for ax, metric in zip(axes, metrics):
        for reuse in reuse_values:
            sub = df[df.min_reuse == reuse]
            ax.plot(sub.threshold, sub[metric], marker="o", label=f"min_reuse={reuse}")
        ax.set_title(metric)
        ax.set_xlabel("risk threshold")
        ax.axvline(55, color="gray", linestyle="--", alpha=0.5, label="current default (55)")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("score")
    axes[0].legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(TESTS_DIR / "sensitivity_sweep.png", dpi=130)

    # Pick best F1 per reuse value, then overall best
    best = df.loc[df.f1.idxmax()]
    print("\n=== Best F1 operating point across the sweep ===")
    print(best.to_dict())

    with open(TESTS_DIR / "sensitivity_summary.json", "w") as f:
        json.dump({
            "best_operating_point": best.to_dict(),
            "note": (
                "Tuned on the same synthetic dataset used for headline metrics. "
                "In production this sweep should run on a separate validation "
                "split, not the reported test set."
            ),
        }, f, indent=2)

    # Restore module defaults and regenerate the "official" results at the
    # ORIGINAL documented threshold, so this sweep doesn't silently change
    # what data/detection_results.json contains.
    importlib.reload(detect_module)
    detect_module.run_detection(str(DATA_DIR / "transactions.csv"))
    print("\nRestored data/detection_results.json to default threshold/reuse settings.")


if __name__ == "__main__":
    main()
