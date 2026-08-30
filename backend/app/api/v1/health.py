"""Health, readiness, and metrics endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import get_current_user
from app.db.neo4j_client import health_check as neo4j_health
from app.db.redis_client import health_check as redis_health
from app.detection.anomaly import is_model_loaded, get_model_metadata

router = APIRouter()

_start_time = datetime.now(timezone.utc)


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "TRACE-X",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": (datetime.now(timezone.utc) - _start_time).total_seconds(),
    }


@router.get("/readiness")
async def readiness() -> Any:
    checks = {}
    all_ok = True

    neo4j_ok = await neo4j_health()
    checks["neo4j"] = "ok" if neo4j_ok else "unavailable"
    if not neo4j_ok:
        all_ok = False

    redis_ok = await redis_health()
    checks["redis"] = "ok" if redis_ok else "unavailable"
    if not redis_ok:
        all_ok = False

    checks["ml_model"] = "loaded" if is_model_loaded() else "not_loaded"

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/metrics")
async def metrics() -> Dict[str, Any]:
    from app.detection.risk_fusion import list_alerts
    from app.detection.pipeline import get_transaction_history

    alerts = list_alerts(limit=10000)
    tx_history = get_transaction_history()
    meta = get_model_metadata() or {}

    severity_counts: Dict[str, int] = {}
    for a in alerts:
        sev = a.severity.value
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "uptime_seconds": (datetime.now(timezone.utc) - _start_time).total_seconds(),
        "transactions_processed": len(tx_history),
        "alerts_total": len(alerts),
        "alerts_by_severity": severity_counts,
        "ml_model_version": meta.get("model_version", "not_loaded"),
        "ml_model_trained_at": meta.get("trained_at"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/reset", tags=["System"])
async def reset_system() -> Dict[str, Any]:
    """Reset all in-memory pipeline state and cache."""
    from app.detection.pipeline import reset_pipeline
    reset_pipeline()
    return {"status": "ok", "message": "Pipeline and database reset successfully."}

