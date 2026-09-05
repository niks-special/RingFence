# RingFence — Fraud-Ring Detection for Payments Platforms

**Track:** AI Risk Manager · Razorpay AI Buildathon 2026

RingFence detects **coordinated fraud rings** — groups of buyer or merchant
accounts that collude by secretly sharing infrastructure (devices, IPs,
payment instruments, settlement bank accounts) — instead of scoring one
transaction at a time. It flags clusters for human review, never auto-blocks,
and every decision comes with a full, human-readable audit trail.

This is graph/network-analysis fraud detection, the same technique real
payment platforms (and network-security teams doing botnet/lateral-movement
detection) use to catch coordinated bad actors that per-transaction ML
models miss.

## Why rings, not single transactions?

A single fraudulent transaction is easy to hide inside normal-looking
behaviour. A **ring** — several accounts secretly sharing the same device,
IP, or settlement account — leaves a structural fingerprint that's much
harder to fake, because it requires real, expensive shared infrastructure.

## How it works

1. **Build a graph.** Buyer accounts are linked if they repeatedly share a
   device, IP, or payment instrument. Merchant accounts are linked if they
   repeatedly share a settlement bank account or registration IP. A resource
   only counts as a signal once it's been *reused* ≥3 times — a single
   incidental collision (e.g. two strangers on the same café wifi, once) is
   normal internet noise, not fraud.
2. **Extract clusters.** Connected components in that graph are candidate
   rings.
3. **Score each cluster** on four explainable, auditable signals:
   - **Resource reuse** — how tightly the cluster reuses a small pool of
     shared infrastructure relative to its size
   - **Velocity** — how bursty its transactions are in time
   - **Structuring** — how much its amounts cluster around round numbers
     (a classic layering signature)
   - **Refund lift** — refund/chargeback rate vs. platform baseline
4. **Combine into a 0–100 risk score** with documented, tunable weights —
   not a black box.
5. **Flag clusters ≥ 55 for review.** This is a bounded, gated action, not
   an auto-block — a wrongly-held merchant has a real cost.
6. **Emit a full audit trail**: which entities, which shared resources,
   which signals fired, and why — for every single decision.

## Results (on synthetic held-out test data)

| Metric | Canonical run (seed 42) | Average across 7 seeds |
|---|---|---|
| Transaction-level precision | **100.0%** (0 false positives) | **100.0%** (std: 0.000) |
| Transaction-level recall | 87.0% | **74.4%** (std: 0.082) |
| F1 | 0.931 | 0.851 |
| Rings caught / embedded | 7 / 8 | ~5.9 / 8 |

We report the multi-seed average, not just the best single run — full
methodology and a red-team evasion test in
[`TESTING.md`](TESTING.md). Precision is completely stable (zero variance
across seeds); recall varies more, which is itself an important, honest
finding, not a footnote.

**Known limitation (found via adversarial testing):** a fraud ring that
uses a fresh device/IP/instrument for every transaction, never reusing
one more than twice, is currently **invisible** to this detector — 0%
caught. Graph formation is the primary gate all four risk signals depend
on; defeating resource reuse alone bypasses everything downstream. This
maps to a real evasion pattern (device farms, disposable virtual cards)
and is the top item on the roadmap below.

Full breakdown, the honest exception list for missed rings, and the
reasoning trail live in
[`notebook/RingFence_Analysis.ipynb`](notebook/RingFence_Analysis.ipynb).
Full test methodology (unit tests, threshold sweep, stability, adversarial,
scale) is in [`TESTING.md`](TESTING.md).

## Project structure

```
ringfence/
├── src/
│   ├── generate_data.py   # synthetic transaction data w/ embedded ground-truth rings
│   ├── detect.py           # the detector: graph construction + risk scoring
│   └── evaluate.py         # precision/recall/F1 + false-positive cost analysis
├── tests/
│   ├── test_unit.py            # 12 unit tests on the scoring signals + graph builder
│   ├── sensitivity_sweep.py    # threshold/reuse sweep -> chosen operating point
│   ├── stability_test.py       # multi-seed variance check
│   └── adversarial_test.py     # red-team evasion test
├── notebook/
│   ├── build_notebook.py
│   └── RingFence_Analysis.ipynb   # full walkthrough with charts
├── dashboard/
│   ├── build_dashboard.py
│   └── index.html          # standalone review console (open directly in a browser)
├── data/                    # generated data + results (see below)
├── TESTING.md               # full test methodology and honest findings
└── docs/
```

## Running it

```bash
pip install -r requirements.txt

python src/generate_data.py    # generates data/transactions.csv + ground_truth.csv
python src/detect.py           # runs the detector -> data/detection_results.json, audit_trail.json
python src/evaluate.py         # scores against held-out ground truth -> data/evaluation_report.json

python dashboard/build_dashboard.py   # rebuilds dashboard/index.html with fresh results
open dashboard/index.html             # or just double-click it
```

The notebook can be re-run top to bottom:
```bash
jupyter nbconvert --to notebook --execute --inplace notebook/RingFence_Analysis.ipynb
```

## Design choices worth knowing about

- **The detector never reads `ground_truth.csv`.** It's generated alongside
  the synthetic data purely so `evaluate.py` can score the detector
  afterwards, the same way a held-out test set works in production.
- **Buyer–merchant edges are deliberately never drawn.** A legitimate buyer
  naturally transacts with many different merchants using their own device —
  treating that as a "link" would flood the graph with noise and collapse
  it into one giant meaningless component. Only same-side sharing
  (buyer↔buyer, merchant↔merchant) is a real collusion signature.
- **Flag-for-review, not auto-block.** Per the brief's bar for this track:
  every money-adjacent action must be explainable, bounded, and gated.
- **Strictly defense-only.** Nothing in this repo is offense-capable; it
  detects and explains, it does not simulate or generate fraud.

## What's next

- **Top priority (found via adversarial testing):** add a resource-reuse-
  independent signal — behavioral/device-fingerprint similarity rather than
  exact ID match — so a ring using disposable devices/IPs can't bypass
  detection entirely just by never reusing a resource more than twice.
- Replace the hand-weighted risk score with a learned model once enough
  labeled review outcomes exist (the audit trail is designed to become
  training data).
- Add a time-decay so old shared-resource evidence weighs less than recent
  reuse.
- Extend merchant-side signals with KYC document hash overlap.
- Vectorize `build_graph`'s row-wise pass for real-time / larger-scale use.
