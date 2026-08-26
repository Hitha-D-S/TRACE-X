"""Transaction ingestion and query endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.detection.pipeline import process_transaction, process_batch, get_transaction_history
from app.models.transaction import TransactionCreate, BatchTransactionCreate

router = APIRouter()


@router.post("", status_code=201)
async def ingest_transaction(
    tx: TransactionCreate,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Ingest a single transaction through the detection pipeline."""
    result = await process_transaction(tx)
    return {
        "id": result.id,
        "final_risk_score": result.final_risk_score,
        "risk_level": result.risk_level,
        "anomaly_score": result.anomaly_score,
        "rule_score": result.rule_score,
        "graph_score": result.graph_score,
        "temporal_score": result.temporal_score,
        "status": "processed",
    }


@router.post("/batch", status_code=201)
async def ingest_batch(
    payload: BatchTransactionCreate,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Batch ingest up to 1000 transactions."""
    result = await process_batch(payload.transactions, dataset_id=payload.dataset_id)
    return result


@router.get("")
async def list_transactions(
    dataset_id: Optional[str] = Query(None),
    min_risk: float = Query(0.0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """List transactions with optional filtering."""
    history = get_transaction_history()

    if dataset_id:
        history = [t for t in history if t.get("dataset_id") == dataset_id]
    if min_risk > 0:
        history = [t for t in history if t.get("final_risk_score", 0) >= min_risk]

    history.sort(key=lambda t: t.get("final_risk_score", 0), reverse=True)
    total = len(history)
    page = history[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "transactions": page,
    }


@router.get("/{tx_id}")
async def get_transaction(
    tx_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a specific transaction by ID."""
    history = get_transaction_history()
    tx = next((t for t in history if t.get("id") == tx_id), None)
    if not tx:
        raise HTTPException(status_code=404, detail=f"Transaction {tx_id} not found")
    return tx
