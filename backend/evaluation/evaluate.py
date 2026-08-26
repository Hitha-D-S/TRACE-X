"""
TRACE-X Evaluation Runner
Runs the full evaluation pipeline:
1. Generates a synthetic dataset.
2. Ingests the synthetic data in batches into the running API.
3. Triggers the detection scoring and alert matching.
4. Calls the evaluation metrics API to pull Precision, Recall, and F1.
5. Prints a detailed, formatted ASCII report.

Usage:
    python evaluation/evaluate.py --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

import httpx

# Add parent path to import generator
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_synthetic import generate_dataset


def run_full_evaluation(api_url: str, normal_count: int, num_accounts: int):
    print("====================================================")
    print(" TRACE-X OFFLINE BENCHMARK & DETECTION EVALUATION")
    print("====================================================")
    print(f"API Target: {api_url}")

    # ── 1. Check API Health ──────────────────────────────────
    print("\n[1/4] Checking API connectivity...")
    try:
        resp = httpx.get(f"{api_url}/api/v1/health", timeout=5.0)
        if resp.status_code != 200:
            print(f"[-] API returned status code {resp.status_code}")
            sys.exit(1)
        print("  [+] Connected to TRACE-X API.")
    except Exception as e:
        print(f"[-] Failed to connect to API at {api_url}: {e}")
        print("   Please start the server first (e.g. uvicorn app.main:app)")
        sys.exit(1)

    # ── 2. Generate Labeled Synthetic Data ────────────────────
    print("\n[2/4] Generating fresh synthetic transaction dataset...")
    dataset = generate_dataset(seed=42, normal_count=normal_count, num_accounts=num_accounts)
    txs = dataset["transactions"]
    print(f"  [+] Generated {len(txs)} synthetic transactions.")

    # ── 3. Ingest Batch to API ────────────────────────────────
    print("\n[3/4] Ingesting transactions into detection pipeline...")
    batch_url = f"{api_url}/api/v1/transactions/batch"
    batch_size = 100
    total_txs = len(txs)

    # Clear current state first via test reset helper if dev mode (skipped if not available)
    try:
        resp = httpx.post(f"{api_url}/api/v1/reset", timeout=10.0)
        if resp.status_code == 200:
            print("  [+] Reset API state.")
        else:
            print(f"  [-] Failed to reset API: {resp.status_code}")
    except Exception as e:
        print(f"  [-] Skipped reset: {e}")

    t_start = time.perf_counter()
    ingested = 0
    for i in range(0, total_txs, batch_size):
        chunk = txs[i : i + batch_size]

        payload = {
            "transactions": chunk,
            "dataset_id": "SYNTHETIC_EVAL",
        }
        try:
            resp = httpx.post(batch_url, json=payload, timeout=30.0)
            if resp.status_code == 201:
                ingested += len(chunk)
                print(f"  Ingested {ingested}/{total_txs} transactions...", end="\r")
            else:
                print(f"\n[-] Batch ingestion failed: {resp.status_code} - {resp.text[:200]}")
                sys.exit(1)
        except Exception as e:
            print(f"\n[-] Network error during batch ingestion: {e}")
            sys.exit(1)

    t_end = time.perf_counter()
    print(f"\n  [+] Batch ingestion complete in {t_end - t_start:.2f}s ({ingested/ (t_end - t_start):.1f} tx/s).")

    # ── 4. Trigger & Pull Evaluation Metrics ──────────────────
    print("\n[4/4] Running detection metrics evaluation...")
    eval_url = f"{api_url}/api/v1/evaluation/run"
    try:
        resp = httpx.post(eval_url, timeout=60.0)
        if resp.status_code != 200:
            print(f"[-] Evaluation run failed: {resp.status_code} - {resp.text}")
            sys.exit(1)
        metrics = resp.json()
    except Exception as e:
        print(f"[-] Network error during evaluation execution: {e}")
        sys.exit(1)

    # ── 5. Print ASCII Performance Report ─────────────────────
    print("\n====================================================")
    print("                PERFORMANCE METRICS REPORT")
    print("====================================================")
    print(f"Evaluation Run: {metrics['run_at']}")
    print(f"Total Transactions Labeled: {metrics['labeled_transactions']}")
    print("----------------------------------------------------")
    print(f"True Positives  (TP): {metrics['true_positives']:4d} | False Positives (FP): {metrics['false_positives']:4d}")
    print(f"False Negatives (FN): {metrics['false_negatives']:4d} | True Negatives  (TN): {metrics['true_negatives']:4d}")
    print("----------------------------------------------------")
    print(f"Precision : {metrics['precision'] * 100:6.2f}% (Ability to avoid false alarms)")
    print(f"Recall    : {metrics['recall'] * 100:6.2f}% (Ability to detect true crime)")
    print(f"F1 Score  : {metrics['f1'] * 100:6.2f}% (Balanced harmonic accuracy)")
    print(f"FPR       : {metrics['false_positive_rate'] * 100:6.2f}% (False Positive Rate)")
    print("====================================================")
    print("                PER-SCENARIO BREAKDOWN")
    print("====================================================")
    print(f"{'Typology Scenario':<26} | {'Precision':<9} | {'Recall':<9} | {'F1':<9}")
    print("-" * 60)

    for scenario, data in metrics["per_scenario"].items():
        if scenario == "NORMAL":
            continue
        print(
            f"{scenario:<26} | "
            f"{data['precision']*100:8.2f}% | "
            f"{data['recall']*100:8.2f}% | "
            f"{data['f1']*100:8.2f}%"
        )
    print("====================================================\n")


def main():
    parser = argparse.ArgumentParser(description="TRACE-X Evaluation Runner")
    parser.add_argument("--api", type=str, default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=200, help="Normal transactions count")
    parser.add_argument("--accounts", type=int, default=30, help="Unique accounts count")
    args = parser.parse_args()

    run_full_evaluation(api_url=args.api, normal_count=args.count, num_accounts=args.accounts)


if __name__ == "__main__":
    main()
