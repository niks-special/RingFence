"""Builds notebook/RingFence_Analysis.ipynb programmatically via nbformat."""
from pathlib import Path
import nbformat as nbf

NOTEBOOK_DIR = Path(__file__).resolve().parent

nb = nbf.v4.new_notebook()
cells = []

cells.append(nbf.v4.new_markdown_cell(
"""# RingFence — Fraud-Ring Detection: Analysis Notebook

**Track:** AI Risk Manager (Razorpay AI Buildathon)
**What this notebook does:** loads the synthetic transaction dataset, runs the
graph-based collusion detector, and evaluates it against held-out ground
truth — precision, recall, F1, ring-level recovery, and an honest
false-positive cost analysis.

The detector never sees `ground_truth.csv` during detection — it is only
used here, afterwards, purely for scoring."""
))

cells.append(nbf.v4.new_code_cell(
"""import sys, json
sys.path.insert(0, '../src')
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

from generate_data import main as regenerate_data
from detect import run_detection, build_graph, WEIGHTS, RISK_THRESHOLD, MIN_RESOURCE_REUSE
import evaluate

pd.set_option('display.max_colwidth', 60)"""
))

cells.append(nbf.v4.new_markdown_cell("## 1. The dataset"))
cells.append(nbf.v4.new_code_cell(
"""df = pd.read_csv('../data/transactions.csv')
gt = pd.read_csv('../data/ground_truth.csv')
print(f"Transactions: {len(df):,}")
print(f"Merchants: {df.merchant_id.nunique():,}  |  Buyers: {df.buyer_id.nunique():,}")
print(f"Ring (fraud) transactions: {gt.is_ring_gt.sum()} ({gt.is_ring_gt.mean():.2%})")
df.head()"""
))

cells.append(nbf.v4.new_markdown_cell(
"""## 2. How detection works

1. Build a graph: buyer↔buyer edges from shared device/IP/instrument,
   merchant↔merchant edges from shared settlement account/registration IP —
   only when a resource is **reused ≥ 3 times** (filters one-off noise).
2. Extract connected clusters (≥3 entities).
3. Score each cluster on four explainable signals: resource reuse,
   transaction velocity (burstiness), amount structuring (round-number
   clustering), and refund-rate lift vs. platform baseline.
4. Flag clusters scoring ≥ 55/100 for **review** (not auto-block — a bounded,
   gated action)."""
))

cells.append(nbf.v4.new_code_cell(
"""print("Signal weights:", WEIGHTS)
print("Risk threshold:", RISK_THRESHOLD)
print("Min resource reuse to count as a link:", MIN_RESOURCE_REUSE)

results = run_detection('../data/transactions.csv')
print(f"\\nClusters found: {results['run_meta']['total_clusters_found']}")
print(f"Clusters flagged for review: {results['run_meta']['clusters_flagged']}")"""
))

cells.append(nbf.v4.new_markdown_cell("## 3. Visualizing the shared-resource graph"))
cells.append(nbf.v4.new_code_cell(
"""G = build_graph(df)
comps = [c for c in nx.connected_components(G) if len(c) >= 2]
print(f"Non-trivial components: {len(comps)}")

fig, ax = plt.subplots(figsize=(10, 7))
colors = []
big_comps = [c for c in comps if len(c) >= 3]
subG = G.subgraph(set().union(*big_comps)) if big_comps else G.subgraph(set())
pos = nx.spring_layout(subG, seed=42, k=0.6)
node_colors = ['#e74c3c' if n.startswith('merchant') else '#3498db' for n in subG.nodes()]
nx.draw_networkx(subG, pos, ax=ax, node_color=node_colors, node_size=180,
                  with_labels=False, edge_color='#888', width=1.2, alpha=0.9)
ax.set_title('Shared-resource clusters (red = merchant, blue = buyer)\\nEach cluster is a candidate collusion ring')
ax.axis('off')
plt.tight_layout()
plt.savefig('../data/graph_clusters.png', dpi=130)
plt.show()"""
))

cells.append(nbf.v4.new_markdown_cell("## 4. Risk scores per cluster"))
cells.append(nbf.v4.new_code_cell(
"""clusters_df = pd.DataFrame(results['clusters'])
clusters_df_display = clusters_df[['cluster_id','n_merchants','n_buyers','n_transactions','risk_score','flagged','action']]
clusters_df_display.sort_values('risk_score', ascending=False)"""
))

cells.append(nbf.v4.new_code_cell(
"""fig, ax = plt.subplots(figsize=(9,5))
sorted_c = clusters_df.sort_values('risk_score', ascending=True)
bar_colors = ['#e74c3c' if f else '#95a5a6' for f in sorted_c.flagged]
ax.barh(sorted_c.cluster_id, sorted_c.risk_score, color=bar_colors)
ax.axvline(RISK_THRESHOLD, color='black', linestyle='--', label=f'Flag threshold ({RISK_THRESHOLD})')
ax.set_xlabel('Risk score (0-100)')
ax.set_title('Cluster risk scores — red = flagged for review')
ax.legend()
plt.tight_layout()
plt.savefig('../data/risk_scores.png', dpi=130)
plt.show()"""
))

cells.append(nbf.v4.new_markdown_cell(
"""## 5. Evaluation against held-out ground truth

This is the section that matters most for the brief: **honest metrics,
including false-positive cost** — not a single cherry-picked match."""
))

cells.append(nbf.v4.new_code_cell(
"""evaluate.main()
with open('../data/evaluation_report.json') as f:
    report = json.load(f)"""
))

cells.append(nbf.v4.new_code_cell(
"""txn = report['transaction_level']
ring = report['ring_level']
cost = report['cost_analysis_inr']

print("=== Transaction-level ===")
print(f"Precision: {txn['precision']:.1%}   Recall: {txn['recall']:.1%}   F1: {txn['f1']:.3f}")
print(f"TP={txn['true_positives']}  FP={txn['false_positives']}  FN={txn['false_negatives']}  TN={txn['true_negatives']}")

print("\\n=== Ring-level ===")
print(f"Embedded rings: {ring['true_rings_embedded']}  |  Caught: {ring['rings_caught']}  |  Missed: {ring['rings_missed_ids']}")
print(f"Ring recall: {ring['ring_recall']:.1%}   Ring precision: {ring['ring_precision']:.1%}")
print(f"False positive clusters: {ring['false_positive_clusters']}")

print("\\n=== Cost analysis (INR, illustrative assumptions documented in evaluate.py) ===")
print(f"Total false-positive cost:   ₹{cost['total_false_positive_cost']:,}")
print(f"Total missed-ring cost:      ₹{cost['total_missed_ring_cost']:,}")
print(f"Net value of running detector: ₹{cost['net_value_of_running_detector']:,}")"""
))

cells.append(nbf.v4.new_markdown_cell(
"""## 6. Honest exception list — the 2 rings we missed

Per the brief: *"Throughput plus measured accuracy plus an honest exception
list."* Here's exactly which rings slipped through and a documented
hypothesis why — this is the failure-mode analysis, not just the headline
number."""
))

cells.append(nbf.v4.new_code_cell(
"""with open('../data/rings_meta.json') as f:
    rings_meta = json.load(f)

missed_ids = set(ring['rings_missed_ids'])
for r in rings_meta:
    if r['ring_id'] in missed_ids:
        n_txn = len(gt[gt.ring_id_gt == r['ring_id']])
        print(f"{r['ring_id']}: {len(r['merchants'])} merchants, {len(r['buyers'])} buyers, "
              f"{len(r['devices'])} devices, {len(r['ips'])} ips -- {n_txn} transactions")
print()
print("Hypothesis: these rings spread a small number of transactions across a")
print("*wider* pool of shared devices/IPs than our other rings, so individual")
print("resource reuse counts sometimes fell below the MIN_RESOURCE_REUSE=3")
print("threshold that gates a graph edge. Lowering that threshold would catch")
print("these but increases false-positive risk from incidental legit overlap")
print("(e.g. shared home wifi) -- a real precision/recall trade-off, tuned")
print("here toward precision since a wrongly-flagged merchant has real cost.")"""
))

cells.append(nbf.v4.new_markdown_cell(
"""## 7. Audit trail sample

Every flagged cluster has a full, traceable audit entry — required for a
"bounded, gated, explainable" action per the brief."""
))

cells.append(nbf.v4.new_code_cell(
"""with open('../data/audit_trail.json') as f:
    audit = json.load(f)
flagged_entry = next(a for a in audit if a['decision'] == 'FLAG_FOR_REVIEW')
print(json.dumps(flagged_entry, indent=2))"""
))

cells.append(nbf.v4.new_markdown_cell(
"""## Summary

| Metric | Value |
|---|---|
| Transaction-level precision | see output above |
| Transaction-level recall | see output above |
| Rings caught / embedded | see output above |
| False positives | see output above |

Every decision is explainable (signal breakdown), bounded (flag-for-review,
never auto-block), and auditable (full evidence trail per cluster)."""
))

nb['cells'] = cells
with open(str(NOTEBOOK_DIR / 'RingFence_Analysis.ipynb'), 'w') as f:
    nbf.write(nb, f)
print("Notebook written.")
