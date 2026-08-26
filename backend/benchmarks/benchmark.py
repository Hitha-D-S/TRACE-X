"""
TRACE-X Pipeline Latency & Throughput Benchmark
Measures processing latency and throughput of the ingestion pipeline.
Outputs percentiles (P50, P90, P95, P99) and transactions/sec.

Usage:
    python benchmarks/benchmark.py --n 100
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from statistics import mean, median

import numpy as np

# Add parent path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.detection.pipeline import process_transaction, reset_pipeline
from app.models.transaction import TransactionCreate


async def run_benchmark(n_samples: int):
    print("====================================================")
    print("      TRACE-X PIPELINE LATENCY BENCHMARK")
    print("====================================================")
    print(f"Executing {n_samples} pipeline runs...")

    reset_pipeline()

    # Create synthetic test transactions
    txs = []
    for i in range(n_samples):
        txs.append(TransactionCreate(
            id=f"TX-BENCH-{i:06d}",
            source_account_id=f"ACC-{i}",
            destination_account_id=f"ACC-{i+1}",
            amount="5000.00",
            currency="INR",
            transaction_type="NEFT",
        ))

    latencies = []

    # Warm-up (2 runs)
    print("\nWarm-up...")
    for i in range(2):
        await process_transaction(txs[i])

    print("Running benchmark...")
    t_start = time.perf_counter()

    for tx in txs:
        t_tx_start = time.perf_counter()
        await process_transaction(tx)
        t_tx_end = time.perf_counter()
        latencies.append((t_tx_end - t_tx_start) * 1000)  # ms

    t_end = time.perf_counter()
    total_time = t_end - t_start

    # Calculate statistics
    avg_lat = mean(latencies)
    med_lat = median(latencies)
    p90 = np.percentile(latencies, 90)
    p95 = np.percentile(latencies, 95)
    p99 = np.percentile(latencies, 99)
    throughput = n_samples / total_time

    print("\n====================================================")
    print("                BENCHMARK RESULTS")
    print("====================================================")
    print(f"Total Transactions processed : {n_samples}")
    print(f"Total Elapsed Time           : {total_time:.4f} seconds")
    print(f"Throughput                   : {throughput:.2f} tx/sec")
    print("----------------------------------------------------")
    print(f"Average Latency              : {avg_lat:.2f} ms")
    print(f"Median (P50) Latency         : {med_lat:.2f} ms")
    print(f"P90 Latency                  : {p90:.2f} ms")
    print(f"P95 Latency                  : {p95:.2f} ms")
    print(f"P99 Latency                  : {p99:.2f} ms")
    print("====================================================\n")


def main():
    parser = argparse.ArgumentParser(description="TRACE-X Pipeline Benchmark")
    parser.add_argument("--n", type=int, default=100, help="Number of transactions to test")
    args = parser.parse_args()

    asyncio.run(run_benchmark(args.n))


if __name__ == "__main__":
    main()
