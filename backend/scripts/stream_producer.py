"""
TRACE-X Transaction Stream Producer
Reads a synthetic dataset and streams transactions to the API at a configurable rate.
Supports direct-API mode (no Kafka needed for demo).

Usage:
    python scripts/stream_producer.py --rate 2 --duration 300
    python scripts/stream_producer.py --file data/synthetic.json --rate 5
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# Default API
API_BASE = "http://localhost:8000"
DEFAULT_FILE = "data/synthetic.json"


def stream_transactions(
    transactions: list,
    rate_per_second: float = 2.0,
    duration_seconds: int = 300,
    api_url: str = API_BASE,
    verbose: bool = True,
):
    """Stream transactions to the TRACE-X API at the given rate."""
    endpoint = f"{api_url}/api/v1/transactions"
    interval = 1.0 / rate_per_second
    start = time.time()
    sent = 0
    errors = 0

    print(f"🚀 Streaming {len(transactions)} transactions at {rate_per_second} tx/s")
    print(f"   API: {endpoint}")
    print(f"   Duration limit: {duration_seconds}s")
    print()

    with httpx.Client(timeout=10.0) as client:
        for tx in transactions:
            if time.time() - start > duration_seconds:
                print(f"\n⏱️  Duration limit reached ({duration_seconds}s)")
                break

            try:
                # Remove non-API fields before sending
                payload = {k: v for k, v in tx.items()
                           if k not in ("is_suspicious", "scenario_label")}
                resp = client.post(endpoint, json=payload)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    sent += 1
                    if verbose:
                        risk = data.get("final_risk_score", 0)
                        level = data.get("risk_level", "LOW")
                        marker = "⚠️ " if risk >= 60 else "  "
                        print(f"{marker} [{sent:4d}] {tx['id'][-8:]} "
                              f"  {tx['amount']:>12,.0f} INR  "
                              f"  Risk: {risk:5.1f} ({level})")
                else:
                    errors += 1
                    if verbose:
                        print(f"  ❌ Error {resp.status_code}: {resp.text[:80]}")

            except httpx.RequestError as e:
                errors += 1
                print(f"  ❌ Connection error: {e}")

            time.sleep(interval)

    elapsed = time.time() - start
    print(f"\n📊 Complete:")
    print(f"   Sent:   {sent}")
    print(f"   Errors: {errors}")
    print(f"   Time:   {elapsed:.1f}s")
    print(f"   Rate:   {sent/elapsed:.2f} tx/s")


def main():
    parser = argparse.ArgumentParser(description="TRACE-X Stream Producer")
    parser.add_argument("--file", type=str, default=DEFAULT_FILE)
    parser.add_argument("--rate", type=float, default=2.0, help="Transactions per second")
    parser.add_argument("--duration", type=int, default=300, help="Max duration in seconds")
    parser.add_argument("--api", type=str, default=API_BASE)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        print(f"   Run: python scripts/generate_synthetic.py first")
        sys.exit(1)

    with open(file_path) as f:
        dataset = json.load(f)

    transactions = dataset.get("transactions", [])
    if not transactions:
        print("❌ No transactions in dataset")
        sys.exit(1)

    # Sort by timestamp (chronological order)
    transactions.sort(key=lambda t: t.get("timestamp", ""))

    stream_transactions(
        transactions=transactions,
        rate_per_second=args.rate,
        duration_seconds=args.duration,
        api_url=args.api,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
