"""Replay endpoints — chronological transaction playback for an alert."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.detection.risk_fusion import get_alert_by_id
from app.detection.pipeline import get_transaction_history

router = APIRouter()


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    from dateutil.parser import parse
    dt = parse(str(ts))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/{alert_id}")
async def get_replay(
    alert_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return ordered replay events for chronological playback.
    The frontend reconstructs graph state at any timeline position.
    """
    alert = get_alert_by_id(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    history = get_transaction_history()

    # Gather all transactions involving this alert's entities
    entity_set = set(alert.entity_ids)
    relevant_txs = [
        t for t in history
        if t.get("source_account_id") in entity_set
        or t.get("destination_account_id") in entity_set
        or t.get("id") in alert.transaction_ids
    ]

    # Sort chronologically
    relevant_txs.sort(key=lambda t: _parse_ts(t.get("timestamp", datetime.now(timezone.utc))))

    events = []
    for seq, tx in enumerate(relevant_txs, start=1):
        # Determine triggered signals for this transaction
        signals = []
        if float(tx.get("final_risk_score", 0)) >= 60:
            if float(tx.get("rule_score", 0)) > 0.3:
                signals.append("RULE_TRIGGERED")
            if float(tx.get("anomaly_score", 0)) > 0.5:
                signals.append("ANOMALY_DETECTED")
            if float(tx.get("temporal_score", 0)) > 0.5:
                signals.append("TEMPORAL_BURST")
            if float(tx.get("graph_score", 0)) > 0.5:
                signals.append("HIGH_CENTRALITY")

        events.append({
            "sequence": seq,
            "transaction_id": tx.get("id", ""),
            "timestamp": str(tx.get("timestamp", "")),
            "source_entity_id": tx.get("source_account_id", ""),
            "destination_entity_id": tx.get("destination_account_id", ""),
            "amount": float(tx.get("amount", 0)),
            "currency": tx.get("currency", "INR"),
            "transaction_type": tx.get("transaction_type", "OTHER"),
            "final_risk_score": float(tx.get("final_risk_score", 0)),
            "signals_triggered": signals,
        })

    start_time = events[0]["timestamp"] if events else None
    end_time = events[-1]["timestamp"] if events else None

    return {
        "alert_id": alert_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity.value,
        "start_time": start_time,
        "end_time": end_time,
        "total_events": len(events),
        "events": events,
    }


@router.get("/{alert_id}/snapshot")
async def get_snapshot(
    alert_id: str,
    sequence: int = Query(..., ge=1),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return graph state snapshot at a specific sequence position.
    Frontend uses this to reconstruct the graph at that point in time.
    """
    replay_data = await get_replay(alert_id, user=user)
    events = replay_data.get("events", [])

    if sequence > len(events):
        raise HTTPException(status_code=400, detail=f"Sequence {sequence} exceeds {len(events)}")

    # All events up to and including sequence
    prior_events = events[:sequence]
    active_event = events[sequence - 1]

    # Build mini-graph state at this snapshot
    nodes: Dict[str, Dict] = {}
    edges = []
    for ev in prior_events:
        for acct_id in (ev["source_entity_id"], ev["destination_entity_id"]):
            if acct_id not in nodes:
                nodes[acct_id] = {"id": acct_id, "risk_score": 0.0}
            nodes[acct_id]["risk_score"] = max(
                nodes[acct_id]["risk_score"], ev["final_risk_score"]
            )
        edges.append({
            "from": ev["source_entity_id"],
            "to": ev["destination_entity_id"],
            "amount": ev["amount"],
            "active": ev["sequence"] == sequence,
            "risk_score": ev["final_risk_score"],
        })

    return {
        "alert_id": alert_id,
        "sequence": sequence,
        "total_sequences": len(events),
        "active_event": active_event,
        "graph_snapshot": {
            "nodes": list(nodes.values()),
            "edges": edges,
        },
    }
