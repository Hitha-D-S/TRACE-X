"""
TRACE-X Synthetic Data Generator
Generates reproducible synthetic transaction datasets with ground-truth labels.

10 suspicious scenarios are injected into a base of normal transactions.
All data is clearly marked as SYNTHETIC — no real PAN, GSTIN, or personal data.

Usage:
    python scripts/generate_synthetic.py --seed 42 --count 500 --output data/synthetic.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from faker import Faker

SYNTHETIC_BANNER = "SYNTHETIC_DATA"


def _fake_account_id(rng: random.Random) -> str:
    prefix = "ACC"
    suffix = "".join([str(rng.randint(0, 9)) for _ in range(10)])
    return f"{prefix}-{suffix}"


def _fake_pan(rng: random.Random) -> str:
    """Generate clearly fake PAN (not a real one)."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return (
        "".join(rng.choices(letters, k=5)) +
        "".join([str(rng.randint(0, 9)) for _ in range(4)]) +
        rng.choice(letters)
    )


def _fake_gstin(rng: random.Random) -> str:
    """Generate clearly fake GSTIN."""
    state = str(rng.randint(1, 35)).zfill(2)
    pan = _fake_pan(rng)
    return f"{state}{pan}1Z{str(rng.randint(1, 9))}"


def _fake_phone(rng: random.Random) -> str:
    return f"+91-{rng.randint(70000, 99999)}{rng.randint(10000, 99999)}"


def _fake_email(rng: random.Random, fake: Faker) -> str:
    domains = ["synth.example", "demo.test", "tracex.synthetic", "fake.invalid"]
    return f"{fake.user_name()}{rng.randint(1, 999)}@{rng.choice(domains)}"


def _ts(base: datetime, offset_seconds: float = 0) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _make_tx(
    src: str,
    dst: str,
    amount: float,
    timestamp: datetime,
    tx_type: str = "NEFT",
    dataset_id: str = "SYNTHETIC",
    is_suspicious: bool = False,
    scenario_label: str = "NORMAL",
) -> Dict[str, Any]:
    return {
        "id": f"TX-{uuid.uuid4().hex[:12].upper()}",
        "source_account_id": src,
        "destination_account_id": dst,
        "amount": round(amount, 2),
        "currency": "INR",
        "timestamp": timestamp.isoformat(),
        "transaction_type": tx_type,
        "channel": "INTERNET",
        "location": "SYNTHETIC",
        "reference": f"REF-{SYNTHETIC_BANNER}",
        "status": "COMPLETED",
        "dataset_id": dataset_id,
        "source": "SYNTHETIC",
        "is_suspicious": is_suspicious,
        "scenario_label": scenario_label,
    }


# ── Normal Transactions Generator ───────────────────────────────

def generate_normal_transactions(
    accounts: List[str],
    rng: random.Random,
    count: int = 500,
    base_time: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Generate realistic-looking normal transactions."""
    if base_time is None:
        base_time = datetime.now(timezone.utc) - timedelta(days=60)

    types = ["NEFT", "IMPS", "UPI", "RTGS"]
    transactions = []

    for _ in range(count):
        src, dst = rng.sample(accounts, 2)
        amount = rng.lognormvariate(9, 1.5)  # realistic log-normal distribution
        amount = min(max(amount, 100), 5_000_000)
        offset_days = rng.uniform(0, 60)
        ts = base_time + timedelta(days=offset_days, hours=rng.uniform(8, 20))

        transactions.append(_make_tx(
            src=src, dst=dst,
            amount=amount,
            timestamp=ts,
            tx_type=rng.choice(types),
            is_suspicious=False,
            scenario_label="NORMAL",
        ))

    return transactions


# ── Scenario 1: Circular Layering ───────────────────────────────

def inject_circular_layering(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    amount: float = 500_000,
    hops: int = 4,
) -> List[Dict[str, Any]]:
    """A → B → C → D → A"""
    cycle = rng.sample(accounts, min(hops, len(accounts)))
    txs = []
    for i, src in enumerate(cycle):
        dst = cycle[(i + 1) % len(cycle)]
        ts = base_time + timedelta(hours=i * 2 + rng.uniform(0, 1))
        txs.append(_make_tx(
            src=src, dst=dst,
            amount=amount * (1 - i * 0.02),  # slight decay
            timestamp=ts,
            tx_type="RTGS",
            is_suspicious=True,
            scenario_label="CIRCULAR_LAYERING",
        ))
    return txs


# ── Scenario 2: Funnel Account ───────────────────────────────────

def inject_funnel_account(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    funnel_count: int = 8,
) -> List[Dict[str, Any]]:
    """Many small inflows → one large outflow."""
    funnel = rng.choice(accounts)
    sources = rng.sample([a for a in accounts if a != funnel], min(funnel_count, len(accounts) - 2))
    drain = rng.choice([a for a in accounts if a != funnel and a not in sources])

    txs = []
    total_in = 0.0
    for i, src in enumerate(sources):
        amount = rng.uniform(5_000, 20_000)
        total_in += amount
        ts = base_time + timedelta(hours=i * 0.5)
        txs.append(_make_tx(
            src=src, dst=funnel,
            amount=amount,
            timestamp=ts,
            tx_type="UPI",
            is_suspicious=True,
            scenario_label="FUNNEL_ACCOUNT",
        ))

    # Single large outflow
    ts = base_time + timedelta(hours=len(sources) * 0.5 + 1)
    txs.append(_make_tx(
        src=funnel, dst=drain,
        amount=total_in * 0.95,
        timestamp=ts,
        tx_type="RTGS",
        is_suspicious=True,
        scenario_label="FUNNEL_ACCOUNT",
    ))
    return txs


# ── Scenario 3: Rapid Pass-Through ───────────────────────────────

def inject_rapid_passthrough(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
) -> List[Dict[str, Any]]:
    """Received → forwarded within minutes."""
    relay = rng.choice(accounts)
    sender = rng.choice([a for a in accounts if a != relay])
    receiver = rng.choice([a for a in accounts if a not in (relay, sender)])
    amount = rng.uniform(100_000, 500_000)

    txs = [
        _make_tx(sender, relay, amount, base_time, tx_type="RTGS",
                 is_suspicious=True, scenario_label="RAPID_PASSTHROUGH"),
        _make_tx(relay, receiver, amount * 0.98,
                 base_time + timedelta(minutes=rng.randint(2, 8)),
                 tx_type="RTGS", is_suspicious=True, scenario_label="RAPID_PASSTHROUGH"),
    ]
    return txs


# ── Scenario 4: Dormant Account Reactivation ─────────────────────

def inject_dormant_reactivation(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    dormancy_days: int = 120,
) -> List[Dict[str, Any]]:
    """Account dormant 120 days suddenly processes large amount."""
    dormant = rng.choice(accounts)
    sender = rng.choice([a for a in accounts if a != dormant])
    receiver = rng.choice([a for a in accounts if a not in (dormant, sender)])
    amount = rng.uniform(500_000, 2_000_000)

    # The dormant account receives then sends
    in_ts = base_time
    out_ts = base_time + timedelta(hours=rng.uniform(1, 6))

    return [
        _make_tx(sender, dormant, amount, in_ts,
                 is_suspicious=True, scenario_label="DORMANT_REACTIVATION"),
        _make_tx(dormant, receiver, amount * 0.95, out_ts,
                 is_suspicious=True, scenario_label="DORMANT_REACTIVATION"),
    ]


# ── Scenario 5: Shared-Metadata Shell Cluster ────────────────────

def inject_shell_cluster(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    cluster_size: int = 5,
) -> List[Dict[str, Any]]:
    """Multiple companies sharing directors/addresses, transacting among themselves."""
    cluster = rng.sample(accounts, min(cluster_size, len(accounts)))
    txs = []
    for i in range(len(cluster) - 1):
        amount = rng.uniform(50_000, 300_000)
        ts = base_time + timedelta(hours=i * 3)
        txs.append(_make_tx(
            cluster[i], cluster[i + 1], amount, ts,
            tx_type="NEFT",
            is_suspicious=True,
            scenario_label="SHARED_METADATA_CLUSTER",
        ))
    return txs


# ── Scenario 6: Transaction Splitting / Structuring ───────────────

def inject_structuring(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    threshold: int = 10_000,
    count: int = 6,
) -> List[Dict[str, Any]]:
    """Repeated amounts just below threshold."""
    src = rng.choice(accounts)
    dsts = rng.sample([a for a in accounts if a != src], min(count, len(accounts) - 1))
    txs = []
    for i, dst in enumerate(dsts):
        amount = threshold - rng.uniform(100, 500)
        ts = base_time + timedelta(hours=i * 0.5)
        txs.append(_make_tx(
            src, dst, amount, ts,
            tx_type="UPI",
            is_suspicious=True,
            scenario_label="STRUCTURING",
        ))
    return txs


# ── Scenario 7: Fan-In / Fan-Out ────────────────────────────────

def inject_fan_in_fan_out(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    fan_size: int = 6,
) -> List[Dict[str, Any]]:
    """Many sources → hub → many destinations."""
    hub = rng.choice(accounts)
    others = [a for a in accounts if a != hub]
    sources = rng.sample(others, min(fan_size, len(others) // 2))
    dests = rng.sample([a for a in others if a not in sources], min(fan_size, len(others) // 2))

    txs = []
    total = 0.0
    for i, src in enumerate(sources):
        amount = rng.uniform(20_000, 100_000)
        total += amount
        txs.append(_make_tx(
            src, hub, amount,
            base_time + timedelta(hours=i),
            is_suspicious=True, scenario_label="FAN_IN_FAN_OUT",
        ))

    # Fan-out
    per_out = total / len(dests)
    for i, dst in enumerate(dests):
        txs.append(_make_tx(
            hub, dst, per_out * rng.uniform(0.9, 1.1),
            base_time + timedelta(hours=len(sources) + i),
            is_suspicious=True, scenario_label="FAN_IN_FAN_OUT",
        ))

    return txs


# ── Scenario 8: Revenue Mismatch ─────────────────────────────────

def inject_revenue_mismatch(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    count: int = 10,
) -> List[Dict[str, Any]]:
    """Account transacts far beyond reasonable expected volume."""
    src = rng.choice(accounts)
    txs = []
    for i in range(count):
        dst = rng.choice([a for a in accounts if a != src])
        amount = rng.uniform(500_000, 2_000_000)
        ts = base_time + timedelta(days=i * 2)
        txs.append(_make_tx(
            src, dst, amount, ts,
            tx_type="RTGS",
            is_suspicious=True,
            scenario_label="REVENUE_MISMATCH",
        ))
    return txs


# ── Scenario 9: Repeated Round Amounts ───────────────────────────

def inject_round_amounts(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    count: int = 6,
) -> List[Dict[str, Any]]:
    """Repeated large round-number transfers."""
    src = rng.choice(accounts)
    round_amounts = [100_000, 500_000, 1_000_000, 250_000, 750_000, 200_000]
    txs = []
    for i in range(min(count, len(round_amounts))):
        dst = rng.choice([a for a in accounts if a != src])
        ts = base_time + timedelta(hours=i * 4)
        txs.append(_make_tx(
            src, dst, round_amounts[i % len(round_amounts)], ts,
            tx_type="RTGS",
            is_suspicious=True,
            scenario_label="ROUND_AMOUNT_PATTERN",
        ))
    return txs


# ── Scenario 10: High-Velocity Burst ────────────────────────────

def inject_high_velocity_burst(
    accounts: List[str],
    rng: random.Random,
    base_time: datetime,
    burst_count: int = 12,
) -> List[Dict[str, Any]]:
    """Many transactions within a short time window."""
    src = rng.choice(accounts)
    txs = []
    for i in range(burst_count):
        dst = rng.choice([a for a in accounts if a != src])
        amount = rng.uniform(1_000, 20_000)
        ts = base_time + timedelta(minutes=i * 3)
        txs.append(_make_tx(
            src, dst, amount, ts,
            tx_type="UPI",
            is_suspicious=True,
            scenario_label="HIGH_VELOCITY_BURST",
        ))
    return txs


# ── Main Generator ───────────────────────────────────────────────

def generate_dataset(
    seed: int = 42,
    normal_count: int = 500,
    num_accounts: int = 50,
) -> Dict[str, Any]:
    """Generate a complete synthetic dataset with all 10 scenarios."""
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)

    # Generate accounts
    accounts = [_fake_account_id(rng) for _ in range(num_accounts)]
    base_time = datetime.now(timezone.utc) - timedelta(days=30)

    # Generate account owners and bank names mapping
    account_metadata = {}
    banks = ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank", "Punjab National Bank", "Canara Bank"]
    for acc in accounts:
        owner_type = rng.choice(["PERSON", "COMPANY"])
        owner_name = fake.name() if owner_type == "PERSON" else fake.company()
        bank_name = rng.choice(banks)
        account_metadata[acc] = {
            "owner_name": owner_name,
            "bank_name": bank_name,
            "owner_type": owner_type
        }

    all_transactions = []

    # Normal transactions
    normal = generate_normal_transactions(accounts, rng, normal_count, base_time)
    all_transactions.extend(normal)

    # Inject all 10 scenarios
    scenarios = [
        ("CIRCULAR_LAYERING", inject_circular_layering(accounts, rng, base_time + timedelta(days=1))),
        ("FUNNEL_ACCOUNT", inject_funnel_account(accounts, rng, base_time + timedelta(days=3))),
        ("RAPID_PASSTHROUGH", inject_rapid_passthrough(accounts, rng, base_time + timedelta(days=5))),
        ("DORMANT_REACTIVATION", inject_dormant_reactivation(accounts, rng, base_time + timedelta(days=7))),
        ("SHARED_METADATA_CLUSTER", inject_shell_cluster(accounts, rng, base_time + timedelta(days=9))),
        ("STRUCTURING", inject_structuring(accounts, rng, base_time + timedelta(days=11))),
        ("FAN_IN_FAN_OUT", inject_fan_in_fan_out(accounts, rng, base_time + timedelta(days=13))),
        ("REVENUE_MISMATCH", inject_revenue_mismatch(accounts, rng, base_time + timedelta(days=15))),
        ("ROUND_AMOUNT_PATTERN", inject_round_amounts(accounts, rng, base_time + timedelta(days=17))),
        ("HIGH_VELOCITY_BURST", inject_high_velocity_burst(accounts, rng, base_time + timedelta(days=19))),
    ]

    suspicious_count = 0
    for label, txs in scenarios:
        all_transactions.extend(txs)
        suspicious_count += len(txs)
        print(f"  [+] {label}: {len(txs)} transactions")

    # Shuffle to mix suspicious among normal
    rng.shuffle(all_transactions)

    # Sort by timestamp for replay
    all_transactions.sort(key=lambda t: t["timestamp"])

    # Enrich transactions with sender/receiver details
    for tx in all_transactions:
        src = tx["source_account_id"]
        dst = tx["destination_account_id"]
        if src in account_metadata:
            tx["sender_name"] = account_metadata[src]["owner_name"]
            tx["source_bank_name"] = account_metadata[src]["bank_name"]
            tx["sender_type"] = account_metadata[src]["owner_type"]
        if dst in account_metadata:
            tx["receiver_name"] = account_metadata[dst]["owner_name"]
            tx["destination_bank_name"] = account_metadata[dst]["bank_name"]
            tx["receiver_type"] = account_metadata[dst]["owner_type"]

    entity_metadata = []
    for acc in accounts:
        meta = account_metadata.get(acc, {})
        entity_metadata.append({
            "id": acc,
            "type": "BankAccount",
            "masked_number": f"****{acc[-4:]}",
            "pan": _fake_pan(rng),
            "phone": _fake_phone(rng),
            "email": _fake_email(rng, fake),
            "dataset_id": "SYNTHETIC",
            "source": "SYNTHETIC",
            "owner_name": meta.get("owner_name", ""),
            "bank_name": meta.get("bank_name", ""),
            "owner_type": meta.get("owner_type", ""),
        })

    return {
        "metadata": {
            "seed": seed,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_transactions": len(all_transactions),
            "normal_transactions": normal_count,
            "suspicious_transactions": suspicious_count,
            "num_accounts": num_accounts,
            "scenarios": [s[0] for s in scenarios],
            "disclaimer": "ALL DATA IS SYNTHETIC. Not for production use.",
            "banner": SYNTHETIC_BANNER,
        },
        "entities": entity_metadata,
        "transactions": all_transactions,
    }


def main():
    parser = argparse.ArgumentParser(description="TRACE-X Synthetic Data Generator")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--accounts", type=int, default=50)
    parser.add_argument("--output", type=str, default="data/synthetic.json")
    args = parser.parse_args()

    print(f"\nGenerating synthetic dataset (seed={args.seed}, normal_txs={args.count})...")
    dataset = generate_dataset(
        seed=args.seed,
        normal_count=args.count,
        num_accounts=args.accounts,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(dataset, f, indent=2, default=str)

    meta = dataset["metadata"]
    print(f"\nDataset generated:")
    print(f"   Total transactions: {meta['total_transactions']}")
    print(f"   Normal: {meta['normal_transactions']}")
    print(f"   Suspicious: {meta['suspicious_transactions']}")
    print(f"   Accounts: {meta['num_accounts']}")
    print(f"   Output: {output_path.absolute()}")
    print(f"\n   To ingest: python scripts/ingest_synthetic.py --file {output_path}")


if __name__ == "__main__":
    main()
