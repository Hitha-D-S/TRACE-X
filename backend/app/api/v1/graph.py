"""Graph query endpoints — network, paths, clusters, what-if."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.security import get_current_user
from app.db.neo4j_client import get_graph_network
from app.db.redis_client import get_graph_cache, set_graph_cache
from app.detection.pipeline import get_graph, get_transaction_history
from app.detection.graph_features import (
    compute_graph_features,
    find_suspicious_paths,
    get_cluster_metrics,
    build_graph,
)

router = APIRouter()


@router.get("/network")
async def get_network(
    dataset_id: Optional[str] = Query(None),
    min_risk: float = Query(0.0, ge=0, le=100),
    limit: int = Query(200, ge=1, le=1000),
    use_cache: bool = Query(True),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Return nodes and edges for the graph visualization.
    Prefers in-memory NetworkX graph; falls back to Neo4j.
    """
    cache_key = dataset_id or "all"
    if use_cache:
        cached = await get_graph_cache(cache_key)
        if cached:
            return cached

    # Build from in-memory history (faster for demo)
    history = get_transaction_history()
    if dataset_id:
        history = [t for t in history if t.get("dataset_id") == dataset_id]

    nodes: Dict[str, Any] = {}
    edges: List[Dict[str, Any]] = []

    for tx in history[:limit * 2]:  # over-fetch, will be capped
        src = tx.get("source_account_id", "")
        dst = tx.get("destination_account_id", "")
        if not src or not dst:
            continue

        risk = tx.get("final_risk_score", 0)
        if risk < min_risk:
            continue



        G = get_graph()
        for acct_id in (src, dst):
            node_attrs = {}
            if G.has_node(acct_id):
                node_attrs = G.nodes[acct_id]

            if acct_id not in nodes:
                nodes[acct_id] = {
                    "id": acct_id,
                    "label": f"...{acct_id[-6:]}",
                    "type": "BankAccount",
                    "risk_score": risk,
                    "dataset_id": tx.get("dataset_id", "SYNTHETIC"),
                    "owner_name": node_attrs.get("owner_name", ""),
                    "bank_name": node_attrs.get("bank_name", ""),
                    "owner_type": node_attrs.get("owner_type", ""),
                }
            else:
                nodes[acct_id]["risk_score"] = max(nodes[acct_id]["risk_score"], risk)
                if not nodes[acct_id].get("owner_name") and node_attrs.get("owner_name"):
                    nodes[acct_id]["owner_name"] = node_attrs["owner_name"]
                if not nodes[acct_id].get("bank_name") and node_attrs.get("bank_name"):
                    nodes[acct_id]["bank_name"] = node_attrs["bank_name"]
                if not nodes[acct_id].get("owner_type") and node_attrs.get("owner_type"):
                    nodes[acct_id]["owner_type"] = node_attrs["owner_type"]

        edges.append({
            "id": tx.get("id", ""),
            "from": src,
            "to": dst,
            "amount": float(tx.get("amount", 0)),
            "currency": tx.get("currency", "INR"),
            "timestamp": str(tx.get("timestamp", "")),
            "final_risk_score": risk,
            "transaction_type": tx.get("transaction_type", "OTHER"),
        })

    # Cap to limit
    node_list = list(nodes.values())[:limit]
    edge_list = edges[:limit * 3]

    result = {
        "nodes": node_list,
        "edges": edge_list,
        "total_nodes": len(node_list),
        "total_edges": len(edge_list),
        "dataset_id": dataset_id,
    }

    await set_graph_cache(cache_key, result)
    return result


@router.get("/path")
async def find_path(
    source: str = Query(...),
    target: str = Query(...),
    max_depth: int = Query(4, ge=1, le=6),
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Find suspicious paths between two entities."""
    G = get_graph()
    paths = find_suspicious_paths(G, source, target, max_depth)
    return {
        "source": source,
        "target": target,
        "paths": paths,
        "path_count": len(paths),
    }


@router.get("/clusters/{cluster_id}")
async def get_cluster(
    cluster_id: str,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get metrics for a named cluster (alert entity set)."""
    from app.detection.risk_fusion import get_alert_by_id
    alert = get_alert_by_id(cluster_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    G = get_graph()
    metrics = get_cluster_metrics(G, alert.entity_ids)
    return {"cluster_id": cluster_id, "entity_ids": alert.entity_ids, **metrics}


class WhatIfRequest(BaseModel):
    cluster_id: str
    excluded_entity_ids: List[str]
    time_window_hours: Optional[int] = None


@router.post("/what-if")
async def what_if_analysis(
    req: WhatIfRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Virtual entity exclusion analysis.
    NEVER modifies stored data — simulation only.
    """
    from app.detection.risk_fusion import get_alert_by_id
    alert = get_alert_by_id(req.cluster_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Cluster {req.cluster_id} not found")

    G = get_graph()

    # Original metrics
    original_metrics = get_cluster_metrics(G, alert.entity_ids)

    # Simulated: remove excluded nodes from a copy
    import networkx as nx
    G_sim = G.copy()
    for excl in req.excluded_entity_ids:
        if excl in G_sim:
            G_sim.remove_node(excl)

    remaining_entities = [e for e in alert.entity_ids if e not in req.excluded_entity_ids]
    simulated_metrics = get_cluster_metrics(G_sim, remaining_entities)

    # Paths removed
    paths_removed = 0
    for excl in req.excluded_entity_ids:
        from itertools import combinations
        other_entities = [e for e in alert.entity_ids if e != excl]
        for other in other_entities:
            orig_paths = find_suspicious_paths(G, excl, other, max_depth=4)
            paths_removed += len(orig_paths)

    risk_change = (
        simulated_metrics.get("max_pagerank", 0) -
        original_metrics.get("max_pagerank", 0)
    )

    return {
        "simulation": True,
        "disclaimer": "This is a virtual simulation — no data has been modified.",
        "cluster_id": req.cluster_id,
        "excluded_entities": req.excluded_entity_ids,
        "original_metrics": original_metrics,
        "simulated_metrics": simulated_metrics,
        "paths_removed": paths_removed,
        "risk_score_change": round(risk_change, 4),
        "entities_remaining": len(remaining_entities),
        "explanation": (
            f"Excluding {len(req.excluded_entity_ids)} entity/entities reduces the "
            f"cluster from {original_metrics.get('node_count', 0)} to "
            f"{simulated_metrics.get('node_count', 0)} nodes and removes "
            f"{original_metrics.get('cycle_count', 0) - simulated_metrics.get('cycle_count', 0)} "
            "detected cycles."
        ),
    }
