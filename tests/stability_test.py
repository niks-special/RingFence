"""
RingFence — Multi-Seed Stability Test
========================================
Runs the full generate -> detect -> evaluate pipeline across several
different random seeds and reports mean/std of precision, recall, F1, and
ring recall. A single seed proving 87% recall means nothing on its own --
this checks whether that number is stable or a fluke.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import importlib
import json

import numpy as np
import pandas as pd

import generate_data
import detect as detect_module

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TESTS_DIR = Path(__file__).resolve().parent

SEEDS = [1, 7, 42, 123, 2026, 31337, 99]


def run_one_seed(seed):
    generate_data.random.seed(seed)
    generate_data.np.random.seed(seed)
    generate_data.main()

    results = detect_module.run_detection(str(DATA_DIR / "transactions.csv"))

    gt = pd.read_csv(DATA_DIR / "ground_truth.csv")
    gt_txn_map = dict(zip(gt.txn_id, gt.is_ring_gt))
    gt_ring_map = dict(zip(gt.txn_id, gt.ring_id_gt))

    predicted = set()
    for c in results["clusters"]:
        if c["flagged"]:
            predicted.update(c["txn_ids"])

    all_ids = set(gt.txn_id)
    tp = sum(1 for t in predicted if gt_txn_map.get(t, False))
    fp = sum(1 for t in predicted if not gt_txn_map.get(t, False))
    fn = sum(1 for t in all_ids if gt_txn_map.get(t, False) and t not in predicted)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    true_rings = set(gt.ring_id_gt.dropna().unique())
    caught = set()
    for c in results["clusters"]:
        if c["flagged"]:
            for t in c["txn_ids"]:
                rid = gt_ring_map.get(t)
                if rid:
                    caught.add(rid)
    ring_recall = len(caught) / len(true_rings) if true_rings else 0.0

    return {
        "seed": seed, "precision": precision, "recall": recall, "f1": f1,
        "ring_recall": ring_recall, "n_rings": len(true_rings), "n_caught": len(caught),
        "fraud_txns": int(gt.is_ring_gt.sum()), "total_txns": len(gt),
    }


def main():
    rows = []
    for seed in SEEDS:
        row = run_one_seed(seed)
        rows.append(row)
        print(f"seed={seed:6d}  P={row['precision']:.3f}  R={row['recall']:.3f}  "
              f"F1={row['f1']:.3f}  rings={row['n_caught']}/{row['n_rings']}")

    df = pd.DataFrame(rows)
    df.to_csv(TESTS_DIR / "stability_results.csv", index=False)

    summary = {
        "n_seeds": len(SEEDS),
        "precision_mean": round(df.precision.mean(), 4),
        "precision_std": round(df.precision.std(), 4),
        "recall_mean": round(df.recall.mean(), 4),
        "recall_std": round(df.recall.std(), 4),
        "f1_mean": round(df.f1.mean(), 4),
        "f1_std": round(df.f1.std(), 4),
        "ring_recall_mean": round(df.ring_recall.mean(), 4),
        "ring_recall_std": round(df.ring_recall.std(), 4),
    }
    print("\n=== Stability summary across", len(SEEDS), "seeds ===")
    print(json.dumps(summary, indent=2))

    with open(TESTS_DIR / "stability_summary.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
