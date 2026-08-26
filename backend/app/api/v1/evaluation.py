"""Evaluation endpoints — detection benchmark metrics."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user

router = APIRouter()

# In-memory store for evaluation results
_evaluation_results: List[Dict[str, Any]] = []


def _safe_precision(tp: int, fp: int) -> float:
    denom = tp + fp
    return tp / denom if denom > 0 else 0.0


def _safe_recall(tp: int, fn: int) -> float:
    denom = tp + fn
    return tp / denom if denom > 0 else 0.0


def _safe_f1(precision: float, recall: float) -> float:
    denom = precision + recall
    return 2 * precision * recall / denom if denom > 0 else 0.0


def _safe_fpr(fp: int, tn: int) -> float:
    denom = fp + tn
    return fp / denom if denom > 0 else 0.0


@router.post("/run")
async def run_evaluation(
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Run detection evaluation against synthetic ground-truth labels.
    Uses the in-memory transaction history with is_suspicious labels.
    """
    from app.detection.pipeline import get_transaction_history
    from app.detection.risk_fusion import list_alerts

    history = get_transaction_history()
    labeled = [t for t in history if t.get("is_suspicious") is not None]

    if not labeled:
        return {
            "status": "no_labeled_data",
            "message": "Run 'generate_synthetic.py' first to create labeled ground-truth data.",
        }

    # Collect only the unique dataset IDs present in the labeled transactions to prevent cross-contamination
    labeled_dataset_ids = {t.get("dataset_id") for t in labeled if t.get("dataset_id")}

    alerts = list_alerts(limit=10000)
    # Filter alerts to only include those belonging to the labeled datasets
    alerts = [a for a in alerts if a.dataset_id in labeled_dataset_ids]

    alerted_tx_ids: set = set()
    for a in alerts:
        alerted_tx_ids.update(a.transaction_ids)

    # Per-transaction evaluation
    tp = fp = fn = tn = 0
    per_scenario: Dict[str, Dict[str, int]] = {}

    for tx in labeled:
        tx_id = tx.get("id", "")
        label = tx.get("is_suspicious", False)
        scenario = tx.get("scenario_label", "NORMAL")

        predicted = tx_id in alerted_tx_ids

        if scenario not in per_scenario:
            per_scenario[scenario] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

        if label and predicted:
            tp += 1
            per_scenario[scenario]["tp"] += 1
        elif not label and predicted:
            fp += 1
            per_scenario[scenario]["fp"] += 1
        elif label and not predicted:
            fn += 1
            per_scenario[scenario]["fn"] += 1
        else:
            tn += 1
            per_scenario[scenario]["tn"] += 1

    precision = _safe_precision(tp, fp)
    recall = _safe_recall(tp, fn)
    f1 = _safe_f1(precision, recall)
    fpr = _safe_fpr(fp, tn)

    # Per-scenario metrics
    per_scenario_metrics = {}
    for scenario, counts in per_scenario.items():
        p = _safe_precision(counts["tp"], counts["fp"])
        r = _safe_recall(counts["tp"], counts["fn"])
        per_scenario_metrics[scenario] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(_safe_f1(p, r), 4),
            **counts,
        }

    from datetime import datetime, timezone
    result = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "labeled_transactions": len(labeled),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fpr, 4),
        "per_scenario": per_scenario_metrics,
    }
    _evaluation_results.append(result)
    return result


@router.get("/latest")
async def get_latest_evaluation(
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if not _evaluation_results:
        raise HTTPException(status_code=404, detail="No evaluation results found. Run /evaluation/run first.")
    return _evaluation_results[-1]
