"""Entity query and resolution endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import get_current_user
from app.detection.pipeline import get_transaction_history
from app.detection.graph_features import build_graph, compute_graph_features

router = APIRouter()


def _build_entity_index(history: List[Dict]) -> Dict[str, Dict]:
    """Build entity index from transaction history."""
    entities: Dict[str, Dict] = {}
    for tx in history:
        for key in ("source_account_id", "destination_account_id"):
            acct_id = tx.get(key, "")
            if not acct_id:
                continue
            if acct_id not in entities:
                entities[acct_id] = {
                    "id": acct_id,
                    "type": "BankAccount",
                    "masked_number": f"****{acct_id[-4:]}",
                    "risk_score": 0.0,
                    "dataset_id": tx.get("dataset_id", "SYNTHETIC"),
                    "transaction_count": 0,
                    "total_volume": 0.0,
                }
            entities[acct_id]["risk_score"] = max(
                entities[acct_id]["risk_score"],
                float(tx.get("final_risk_score", 0))
            )
            entities[acct_id]["transaction_count"] += 1
            entities[acct_id]["total_volume"] += float(tx.get("amount", 0))
    return entities


@router.get("")
async def list_entities(
    dataset_id: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    min_risk: float = Query(0.0, ge=0, le=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """List entities derived from transaction history."""
    history = get_transaction_history()
    entities = _build_entity_index(history)

    result = list(entities.values())
    if dataset_id:
        result = [e for e in result if e.get("dataset_id") == dataset_id]
    if min_risk > 0:
        result = [e for e in result if e.get("risk_score", 0) >= min_risk]

    result.sort(key=lambda e: e.get("risk_score", 0), reverse=True)
    total = len(result)
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entities": result[offset:offset + limit],
    }


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    history = get_transaction_history()
    entities = _build_entity_index(history)
    entity = entities.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return entity


@router.get("/{entity_id}/relationships")
async def get_entity_relationships(
    entity_id: str,
    max_depth: int = Query(2, ge=1, le=4),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    from app.db.neo4j_client import get_entity_relationships
    return await get_entity_relationships(entity_id, max_depth)


@router.get("/{entity_id}/risk")
async def get_entity_risk(
    entity_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    from app.core.config import get_settings
    settings = get_settings()
    history = get_transaction_history()
    entities = _build_entity_index(history)
    entity = entities.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

    G = build_graph(history)
    feats = compute_graph_features(G, entity_id)
    risk_score = entity.get("risk_score", 0)
    risk_level = settings.get_risk_level(risk_score)

    from app.detection.risk_fusion import list_alerts
    alerts = [
        a for a in list_alerts(limit=1000)
        if entity_id in a.entity_ids
    ]

    return {
        "entity_id": entity_id,
        "entity_type": "BankAccount",
        "risk_score": risk_score,
        "risk_level": risk_level,
        "graph_features": feats.to_dict(),
        "triggered_alerts": [a.id for a in alerts],
        "contributing_factors": [
            f"cycle_count={feats.cycle_count}",
            f"betweenness={feats.betweenness:.4f}",
            f"pagerank={feats.pagerank:.4f}",
        ],
        "related_entities": list(set(
            e for a in alerts for e in a.entity_ids if e != entity_id
        ))[:10],
        "explanation": (
            f"Entity {entity_id[-8:]} has a risk score of {risk_score:.1f}/100 "
            f"({risk_level}). It participates in {len(alerts)} alert(s) and has "
            f"{feats.cycle_count} cycle(s) in the transaction network."
        ),
    }


from app.models.entity import EntityResolutionRequest

@router.post("/resolve")
async def resolve_entities(
    req: EntityResolutionRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Basic entity resolution — find shared attributes between entities."""
    history = get_transaction_history()
    entities = _build_entity_index(history)

    matches = []
    for i, id_a in enumerate(req.entity_ids):
        for id_b in req.entity_ids[i + 1:]:
            shared = []
            # Check shared counterparties
            a_counterparties = set(
                t.get("destination_account_id")
                for t in history if t.get("source_account_id") == id_a
            )
            b_counterparties = set(
                t.get("destination_account_id")
                for t in history if t.get("source_account_id") == id_b
            )
            common = a_counterparties & b_counterparties
            if common:
                shared.append(f"shared_counterparties:{len(common)}")

            score = len(shared) / 5.0  # normalize
            if shared:
                matches.append({
                    "entity_a_id": id_a,
                    "entity_b_id": id_b,
                    "match_score": min(score, 1.0),
                    "confidence": "LOW" if score < 0.3 else "MEDIUM" if score < 0.7 else "HIGH",
                    "matched_attributes": shared,
                    "requires_review": True,
                    "explanation": f"Entities share {len(shared)} common attribute(s): {', '.join(shared)}",
                })

    return {"entity_ids": req.entity_ids, "matches": matches, "match_count": len(matches)}
