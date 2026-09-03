"""
RingFence — Synthetic Data Generator
=====================================
Generates a synthetic payments dataset that mimics Razorpay-style merchant/
buyer transaction flows, with a known set of ground-truth "fraud rings"
embedded inside otherwise-normal traffic.

A fraud ring here = a set of merchants and/or buyers that collude via
shared infrastructure to launder money or run fake-return / chargeback
scams:
  - Buyer-side collusion signal : shared device / IP / payment instrument
    across DIFFERENT buyer accounts (classic mule-account signature).
  - Merchant-side collusion signal : shared settlement bank account /
    registration IP across DIFFERENT merchant accounts (classic
    shell-merchant-network signature).

These are modelled as persistent, entity-owned attributes (not re-rolled
per transaction) because that's how real payment platforms actually see
this signal -- a buyer's device or a merchant's settlement account doesn't
change transaction-to-transaction, so incidental legit collisions stay
rare while ring-internal reuse stays high and detectable.

Ground truth is saved separately so the detector never reads it during
inference -- only used afterwards for scoring (precision/recall/F1/cost).
"""

import json
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

random.seed(42)
np.random.seed(42)

N_MERCHANTS = 260
N_LEGIT_BUYERS = 4000
N_RINGS = 8                 # number of embedded collusion rings
RING_SIZE_RANGE = (4, 9)    # merchants+buyers per ring
N_TRANSACTIONS_LEGIT = 9000
N_TRANSACTIONS_RING_MULT = 14  # avg transactions per ring (high velocity, the tell)


def rand_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def gen_entities():
    merchants = [rand_id("mer") for _ in range(N_MERCHANTS)]
    buyers = [rand_id("buy") for _ in range(N_LEGIT_BUYERS)]
    return merchants, buyers


def gen_merchant_profiles(merchants):
    """Each merchant has its OWN persistent settlement bank account and
    onboarding/registration IP -- set once at signup, not per transaction.
    This is the real-world signal used to catch shell-merchant rings:
    several 'different' storefronts secretly settling to the same bank
    account or registered from the same IP."""
    profiles = {}
    for m in merchants:
        profiles[m] = {
            "settlement_account": rand_id("acct"),
            "registration_ip": rand_id("regip"),
        }
    return profiles


def gen_buyer_profiles(buyers):
    """Each buyer overwhelmingly uses THEIR OWN device/IP/instrument, not a
    random one each transaction (85% one device, 15% two -- phone+laptop;
    80% one IP, 20% two -- home+mobile data). This keeps incidental
    cross-entity collisions realistically low, so any large shared-resource
    cluster later is a genuine signal rather than sampling noise."""
    profiles = {}
    for b in buyers:
        n_dev = 1 if random.random() < 0.85 else 2
        n_ip = 1 if random.random() < 0.80 else 2
        profiles[b] = {
            "devices": [rand_id("dev") for _ in range(n_dev)],
            "ips": [rand_id("ip") for _ in range(n_ip)],
            "instrument": rand_id("pi"),  # one primary card/UPI per buyer
        }
    return profiles


def gen_rings(merchants, buyers):
    """Carve out N_RINGS disjoint collusion rings from the entity pool.
    Each ring gets its OWN tiny shared pool of buyer-side resources
    (devices/ips/instruments) AND merchant-side resources (settlement
    accounts/registration ips) -- that cross-entity reuse is the fraud
    signature the detector is built to find."""
    rings = []
    used_m, used_b = set(), set()
    for i in range(N_RINGS):
        size = random.randint(*RING_SIZE_RANGE)
        n_m = max(2, size // 2)
        n_b = size - n_m
        ring_m = random.sample([m for m in merchants if m not in used_m], n_m)
        ring_b = random.sample([b for b in buyers if b not in used_b], n_b)
        used_m.update(ring_m)
        used_b.update(ring_b)

        ring_devices = [rand_id("dev") for _ in range(random.randint(2, 4))]
        ring_ips = [rand_id("ip") for _ in range(random.randint(2, 4))]
        ring_instr = [rand_id("pi") for _ in range(random.randint(2, 3))]
        ring_accounts = [rand_id("acct") for _ in range(random.randint(1, 2))]
        ring_reg_ips = [rand_id("regip") for _ in range(random.randint(1, 2))]

        rings.append({
            "ring_id": f"ring_{i:02d}",
            "merchants": ring_m,
            "buyers": ring_b,
            "devices": ring_devices,
            "ips": ring_ips,
            "instruments": ring_instr,
            "settlement_accounts": ring_accounts,
            "registration_ips": ring_reg_ips,
        })
    return rings


def gen_legit_transactions(merchants, buyers, buyer_profiles, merchant_profiles):
    rows = []
    start = datetime(2026, 6, 1)
    for _ in range(N_TRANSACTIONS_LEGIT):
        m = random.choice(merchants)
        b = random.choice(buyers)
        bp = buyer_profiles[b]
        mp = merchant_profiles[m]
        ts = start + timedelta(
            days=random.randint(0, 60),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        amount = round(np.random.lognormal(mean=6.5, sigma=0.9), 2)
        status = np.random.choice(
            ["success", "failed", "refunded"], p=[0.90, 0.06, 0.04]
        )
        rows.append({
            "txn_id": rand_id("txn"),
            "merchant_id": m,
            "buyer_id": b,
            "device_id": random.choice(bp["devices"]),
            "ip_id": random.choice(bp["ips"]),
            "instrument_id": bp["instrument"],
            "settlement_account": mp["settlement_account"],
            "registration_ip": mp["registration_ip"],
            "amount_inr": amount,
            "status": status,
            "timestamp": ts.isoformat(),
            "is_ring_gt": False,
            "ring_id_gt": None,
        })
    return rows


def gen_ring_transactions(rings):
    rows = []
    start = datetime(2026, 6, 1)
    for ring in rings:
        entities_m = ring["merchants"]
        entities_b = ring["buyers"]
        n_txn = random.randint(
            N_TRANSACTIONS_RING_MULT - 5, N_TRANSACTIONS_RING_MULT + 8
        )
        burst_day = random.randint(5, 55)
        for _ in range(n_txn):
            m = random.choice(entities_m)
            b = random.choice(entities_b)
            ts = start + timedelta(
                days=burst_day,
                hours=random.randint(0, 3),   # tight burst window
                minutes=random.randint(0, 59),
                seconds=random.randint(0, 59),
            )
            base = random.choice([999, 1999, 4999, 9999, 14999])
            amount = round(base * np.random.uniform(0.97, 1.03), 2)
            status = np.random.choice(
                ["success", "refunded"], p=[0.75, 0.25]  # inflated refund rate
            )
            rows.append({
                "txn_id": rand_id("txn"),
                "merchant_id": m,
                "buyer_id": b,
                "device_id": random.choice(ring["devices"]),
                "ip_id": random.choice(ring["ips"]),
                "instrument_id": random.choice(ring["instruments"]),
                "settlement_account": random.choice(ring["settlement_accounts"]),
                "registration_ip": random.choice(ring["registration_ips"]),
                "amount_inr": amount,
                "status": status,
                "timestamp": ts.isoformat(),
                "is_ring_gt": True,
                "ring_id_gt": ring["ring_id"],
            })
    return rows


def main():
    merchants, buyers = gen_entities()
    rings = gen_rings(merchants, buyers)
    buyer_profiles = gen_buyer_profiles(buyers)
    merchant_profiles = gen_merchant_profiles(merchants)

    # Ring entities are dedicated fraud accounts -- they don't also run a
    # separate genuine business on the side. Excluding them from the legit
    # pool keeps the collusion signal clean and matches how these rings
    # actually operate (freshly onboarded shell accounts, not established
    # merchants with a long legit history).
    ring_merchant_ids = {m for r in rings for m in r["merchants"]}
    ring_buyer_ids = {b for r in rings for b in r["buyers"]}
    legit_merchants = [m for m in merchants if m not in ring_merchant_ids]
    legit_buyers = [b for b in buyers if b not in ring_buyer_ids]

    legit_rows = gen_legit_transactions(legit_merchants, legit_buyers, buyer_profiles, merchant_profiles)
    ring_rows = gen_ring_transactions(rings)

    all_rows = legit_rows + ring_rows
    random.shuffle(all_rows)
    df = pd.DataFrame(all_rows)
    df = df.sort_values("timestamp").reset_index(drop=True)

    df.to_csv(str(DATA_DIR / "transactions.csv"), index=False)

    gt = df[["txn_id", "is_ring_gt", "ring_id_gt"]]
    gt.to_csv(str(DATA_DIR / "ground_truth.csv"), index=False)

    with open(str(DATA_DIR / "rings_meta.json"), "w") as f:
        json.dump(rings, f, indent=2)

    print(f"Generated {len(df)} transactions")
    print(f"  Legit: {len(legit_rows)}  |  Ring (fraud): {len(ring_rows)}")
    print(f"  Embedded rings: {len(rings)}")
    print(f"  Fraud txn rate: {len(ring_rows)/len(df):.2%}")


if __name__ == "__main__":
    main()
