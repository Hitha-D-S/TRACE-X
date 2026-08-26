"""Alert management endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.security import get_current_user
from app.detection.risk_fusion import list_alerts, get_alert_by_id
from app.models.alert import AlertUpdate, AlertNoteCreate, AlertStatus

router = APIRouter()


@router.get("")
async def list_alerts_endpoint(
    dataset_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_risk: float = Query(0.0, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """List alerts with filtering, sorting, and pagination."""
    alerts = list_alerts(
        dataset_id=dataset_id,
        min_risk=min_risk,
        severity=severity,
        limit=10000,  # fetch all then paginate
    )

    if status:
        alerts = [a for a in alerts if a.status.value == status]

    total = len(alerts)
    page = alerts[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "alerts": [a.model_dump() for a in page],
    }


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get detailed alert with full evidence."""
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert.model_dump()


@router.patch("/{alert_id}")
async def update_alert(
    alert_id: str,
    update: AlertUpdate,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Update alert status, assignee, or resolution."""
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    if update.status:
        alert.status = update.status
    if update.assigned_to:
        alert.assigned_to = update.assigned_to
    if update.resolution:
        alert.resolution = update.resolution
    if update.investigator_notes:
        alert.investigator_notes = update.investigator_notes
    alert.updated_at = datetime.now(timezone.utc)

    return {"id": alert.id, "status": alert.status.value, "message": "Updated"}


@router.post("/{alert_id}/assign")
async def assign_alert(
    alert_id: str,
    assignee: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.assigned_to = assignee
    alert.status = AlertStatus.INVESTIGATING
    alert.updated_at = datetime.now(timezone.utc)
    return {"id": alert.id, "assigned_to": assignee, "status": alert.status.value}


@router.post("/{alert_id}/notes")
async def add_note(
    alert_id: str,
    note: AlertNoteCreate,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    existing = alert.investigator_notes or ""
    timestamp = datetime.now(timezone.utc).isoformat()
    alert.investigator_notes = f"{existing}\n[{timestamp}] {user['name']}: {note.content}".strip()
    return {"id": alert.id, "message": "Note added"}


@router.post("/{alert_id}/close")
async def close_alert(
    alert_id: str,
    resolution: str = "Investigated and closed",
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    alert.status = AlertStatus.RESOLVED
    alert.resolution = resolution
    alert.updated_at = datetime.now(timezone.utc)
    return {"id": alert.id, "status": "RESOLVED"}
