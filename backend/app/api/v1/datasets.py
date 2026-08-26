"""Dataset listing endpoint."""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.detection.pipeline import get_transaction_history

router = APIRouter()


@router.get("")
async def list_datasets(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """List all datasets (synthetic + uploaded) with summary counts."""
    history = get_transaction_history()

    datasets: Dict[str, Dict[str, Any]] = {}
    for tx in history:
        did = tx.get("dataset_id", "SYNTHETIC")
        if did not in datasets:
            datasets[did] = {
                "dataset_id": did,
                "source": tx.get("source", "SYNTHETIC"),
                "row_count": 0,
                "entity_count": set(),
                "created_at": str(tx.get("timestamp", "")),
            }
        datasets[did]["row_count"] += 1
        datasets[did]["entity_count"].add(tx.get("source_account_id", ""))
        datasets[did]["entity_count"].add(tx.get("destination_account_id", ""))

    result = []
    for did, d in datasets.items():
        result.append({
            "dataset_id": did,
            "source": d["source"],
            "row_count": d["row_count"],
            "entity_count": len(d["entity_count"]),
            "created_at": d["created_at"],
        })

    result.sort(key=lambda d: d["row_count"], reverse=True)
    return {"datasets": result, "total": len(result)}
