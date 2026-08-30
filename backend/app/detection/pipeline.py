"""
TRACE-X Pipeline — Main transaction processing pipeline.
Ties together: validation → buffer → feature extraction → rule/ML/graph/temporal → risk fusion → alert.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.db import redis_client
from app.db import neo4j_client
from app.detection import rules as rule_engine
from app.detection import anomaly as anomaly_engine
from app.detection import temporal as temporal_engine
from app.detection import graph_features as graph_engine
from app.detection import risk_fusion
from app.models.transaction import TransactionCreate, TransactionFull
from app.models.alert import Alert

logger = get_logger(__name__)
settings = get_settings()

from collections import defaultdict

# Partitioned state dictionaries keyed by dataset_id to isolate datasets
_graphs: Dict[str, nx.MultiDiGraph] = defaultdict(nx.MultiDiGraph)
_transaction_histories: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
_account_last_activities: Dict[str, Dict[str, datetime]] = defaultdict(dict)

MAX_HISTORY = 10_000  # cap in-memory history per dataset

def _get_dataset_key(tx_dict: Dict[str, Any]) -> str:
    return tx_dict.get("dataset_id") or "SYNTHETIC"


async def process_transaction(
    tx: TransactionCreate,
    correlation_id: Optional[str] = None,
) -> TransactionFull:
    """
    Full pipeline for a single transaction.
    1. Idempotency check
    2. Add to in-memory graph
    3. Feature extraction
    4. Rule + ML + temporal + graph scoring
    5. Risk fusion
    6. Alert generation + pub/sub
    7. Neo4j write
    Returns the enriched TransactionFull.
    """
    t_start = time.perf_counter()
    cid = correlation_id or str(uuid.uuid4())[:8]

    tx_dict = tx.model_dump()
    tx_id = tx_dict["id"]
    ds_key = _get_dataset_key(tx_dict)

    # ── 1. Idempotency ───────────────────────────────────────
    if await redis_client.is_already_processed(tx_id):
        logger.info("tx_duplicate_skipped", tx_id=tx_id, cid=cid)
        # Return existing from history if available
        existing = next((t for t in _transaction_histories[ds_key] if t.get("id") == tx_id), None)
        if existing:
            return TransactionFull(**existing)

    # ── 2. Update in-memory graph and history ────────────────
    _add_to_graph(tx_dict)
    _transaction_histories[ds_key].append(tx_dict)
    if len(_transaction_histories[ds_key]) > MAX_HISTORY:
        _transaction_histories[ds_key].pop(0)

    # ── 3. Feature Extraction ────────────────────────────────
    from app.detection.rules import _parse_ts
    tx_ts = _parse_ts(tx_dict.get("timestamp", datetime.now(timezone.utc)))
    recent_txs = _get_recent_txs(ref_ts=tx_ts, hours=24, dataset_id=ds_key)

    # Anomaly score
    anomaly_score, top_features_raw = anomaly_engine.score_transaction(
        tx_dict, _transaction_histories[ds_key][:-1]  # exclude current tx
    )
    top_feature_names = [f[0] for f in top_features_raw]

    # Temporal score
    temporal_score = temporal_engine.compute_transaction_temporal_score(
        tx_dict, _transaction_histories[ds_key]
    )

    # Graph score
    graph_scores = graph_engine.compute_batch_graph_scores(recent_txs)
    src_graph = graph_scores.get(tx_dict["source_account_id"], 0.0)
    dst_graph = graph_scores.get(tx_dict["destination_account_id"], 0.0)
    graph_score = max(src_graph, dst_graph)

    # ── 4. Rule Detection ────────────────────────────────────
    # Ground-truth scenario_label checks are completely removed to prevent leakage.
    # Last activity map is built purely from historical event sequencing.
    entities = _build_entities_from_history(_transaction_histories[ds_key])

    rule_evidences = rule_engine.run_all_rules(
        transactions=_transaction_histories[ds_key],
        graph=_graphs[ds_key],
        entities=entities,
        account_last_activity=_account_last_activities[ds_key],
    )
    # Update last activity AFTER running rules to preserve dormancy gap
    _update_account_last_activity(tx_dict)

    # Filter strictly to relevant rules by transaction_ids
    relevant_evidences = [
        e for e in rule_evidences
        if tx_id in e.transaction_ids
    ]

    # ── 5. Risk Fusion ───────────────────────────────────────
    rule_score = risk_fusion.compute_rule_score(relevant_evidences)

    tx_final_score = round(max(
        (
            settings.risk_weight_rule * rule_score +
            settings.risk_weight_anomaly * anomaly_score +
            settings.risk_weight_graph * graph_score +
            settings.risk_weight_temporal * temporal_score
        ),
        rule_score * 0.60
    ) * 100, 2)
    risk_level = settings.get_risk_level(tx_final_score)

    # Create enriched transaction
    full_tx = TransactionFull(
        **tx_dict,
        anomaly_score=round(anomaly_score, 4),
        rule_score=round(rule_score, 4),
        temporal_score=round(temporal_score, 4),
        graph_score=round(graph_score, 4),
        final_risk_score=tx_final_score,
        risk_level=risk_level,
    )

    # Update history with scores
    _transaction_histories[ds_key][-1].update(full_tx.model_dump())

    # ── 6. Alert Generation ──────────────────────────────────
    alert: Optional[Alert] = None
    if relevant_evidences or anomaly_score > 0.88 or tx_final_score >= 60:
        alert_type = risk_fusion.determine_alert_type(relevant_evidences)
        
        all_tx_ids = {tx_id}
        all_entity_ids = {tx_dict["source_account_id"], tx_dict["destination_account_id"]}
        for e in relevant_evidences:
            all_tx_ids.update(e.transaction_ids)
            all_entity_ids.update(e.entity_ids)

        alert = risk_fusion.fuse_risk_scores(
            rule_evidences=relevant_evidences,
            anomaly_score=anomaly_score,
            graph_score=graph_score,
            temporal_score=temporal_score,
            entity_ids=list(all_entity_ids),
            transaction_ids=list(all_tx_ids),
            alert_type=alert_type,
            dataset_id=tx_dict.get("dataset_id", "SYNTHETIC"),
            top_features=top_feature_names,
            model_version=anomaly_engine.get_model_metadata().get("model_version") if anomaly_engine.get_model_metadata() else None,
            ref_timestamp=tx_ts,
        )
        if alert:
            await redis_client.publish_alert(alert.to_brief_dict())
            # Fallback direct broadcast to active WebSocket clients
            from app.api.v1.websocket import broadcast_alert
            await broadcast_alert(alert.to_brief_dict())
    # ── 7. Neo4j Write (async, non-blocking background task) ─
    async def _async_neo4j_write():
        try:
            await neo4j_client.upsert_transaction_graph(full_tx.to_neo4j_params())
        except Exception as e:
            logger.warning("neo4j_write_failed", tx_id=tx_id, error=str(e))
    import asyncio
    asyncio.create_task(_async_neo4j_write())

    # ── Mark processed ───────────────────────────────────────
    await redis_client.mark_processed(tx_id)

    t_end = time.perf_counter()
    latency_ms = round((t_end - t_start) * 1000, 2)
    logger.info(
        "tx_processed",
        tx_id=tx_id,
        score=tx_final_score,
        risk_level=risk_level,
        alert_generated=alert is not None,
        latency_ms=latency_ms,
        cid=cid,
    )

    return full_tx



async def process_batch(
    transactions: List[TransactionCreate],
    dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a batch of transactions through the pipeline."""
    # Auto-train the ML anomaly model on a dedicated baseline if model is not loaded yet
    if len(transactions) >= 50:
        try:
            from app.detection import anomaly
            if not anomaly.is_model_loaded():
                import json
                from pathlib import Path
                base_dir = Path(__file__).resolve().parent.parent.parent
                train_file = base_dir / "data" / "train_baseline.json"
                if train_file.exists():
                    with open(train_file, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    tx_dicts = d.get("transactions", [])
                    if tx_dicts:
                        anomaly.train_model(tx_dicts)
                anomaly.load_model()
        except Exception as e:
            logger.warning("auto_train_failed", error=str(e))

    results = []
    alerts_generated = 0
    t_start = time.perf_counter()

    for tx in transactions:
        if dataset_id:
            tx.dataset_id = dataset_id
        result = await process_transaction(tx)
        results.append(result)

    # Run batch-level rule detection across all transactions at once
    batch_dicts = [t.model_dump() for t in results]
    ds_key = dataset_id or "SYNTHETIC"
    entities = _build_entities_from_history(_transaction_histories[ds_key])
    batch_rules = rule_engine.run_all_rules(
        transactions=_transaction_histories[ds_key],
        graph=_graphs[ds_key],
        entities=entities,
        account_last_activity=_account_last_activities[ds_key],
    )

    # Generate cluster-level alerts for batch-level findings
    batch_tx_ids = {t["id"] for t in batch_dicts}
    for evidence in batch_rules:
        # Only alert if the evidence involves at least one transaction from the current batch
        if evidence.score >= 0.5 and any(tid in batch_tx_ids for tid in evidence.transaction_ids):
            from dateutil.parser import parse
            # Find the max timestamp in the batch to make it deterministic
            batch_tx_times = []
            for t in batch_dicts:
                ts_val = t.get("timestamp")
                if ts_val:
                    if isinstance(ts_val, str):
                        ts_val = parse(ts_val)
                    batch_tx_times.append(ts_val)
            ref_ts = max(batch_tx_times) if batch_tx_times else datetime.now(timezone.utc)

            alert = risk_fusion.fuse_risk_scores(
                rule_evidences=[evidence],
                anomaly_score=0.0,
                graph_score=0.0,
                temporal_score=0.0,
                entity_ids=evidence.entity_ids,
                transaction_ids=evidence.transaction_ids,
                alert_type=evidence.rule_id,
                dataset_id=dataset_id or "SYNTHETIC",
                ref_timestamp=ref_ts,
            )
            if alert:
                alerts_generated += 1
                await redis_client.publish_alert(alert.to_brief_dict())

    t_end = time.perf_counter()
    return {
        "processed": len(results),
        "alerts_generated": alerts_generated,
        "latency_ms": round((t_end - t_start) * 1000, 2),
        "transactions": [t.model_dump() for t in results],
    }


def _build_entities_from_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build entity list from transaction history to feed the rules engine.
    Extracts custom metadata from transaction reference fields (clean & label-free).
    """
    entities_map: Dict[str, Any] = {}
    for tx in history:
        ref = tx.get("reference", "")
        # Parse reference for metadata tags
        # e.g. REF-SHARED-METADATA:PAN=PAN-SHARED-SHELL-CLUSTER;PHONE=PHONE-SHARED-SHELL-CLUSTER...
        # e.g. REF-ANNUAL-REVENUE:100000
        ref_metadata = {}
        if isinstance(ref, str):
            if "REF-SHARED-METADATA:" in ref:
                parts = ref.split("REF-SHARED-METADATA:", 1)[1].split(";")
                for p in parts:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        ref_metadata[k.lower().strip()] = v.strip()
            elif "REF-ANNUAL-REVENUE:" in ref:
                try:
                    val_str = ref.split("REF-ANNUAL-REVENUE:", 1)[1].strip()
                    ref_metadata["annual_revenue"] = float(val_str)
                except Exception:
                    pass

        for prefix, role in [("sender", "source"), ("receiver", "destination")]:
            acct_id = tx.get(f"{role}_account_id")
            if not acct_id:
                continue
            if acct_id not in entities_map:
                entities_map[acct_id] = {
                    "id": acct_id,
                    "pan": f"PAN-{acct_id}",
                    "phone": f"PHONE-{acct_id}",
                    "email": f"email-{acct_id}@demo.test",
                    "address": f"Address-{acct_id}",
                    "annual_revenue": (
                        120_000_000.0 if tx.get(f"{prefix}_type") == "COMPANY"
                        else 12_000_000.0
                    ),
                }

            # Apply any parsed metadata from the reference field of transactions involving this account
            if "pan" in ref_metadata:
                entities_map[acct_id]["pan"] = ref_metadata["pan"]
            if "phone" in ref_metadata:
                entities_map[acct_id]["phone"] = ref_metadata["phone"]
            if "email" in ref_metadata:
                entities_map[acct_id]["email"] = ref_metadata["email"]
            if "address" in ref_metadata:
                entities_map[acct_id]["address"] = ref_metadata["address"]
            if "annual_revenue" in ref_metadata:
                entities_map[acct_id]["annual_revenue"] = ref_metadata["annual_revenue"]

    return list(entities_map.values())


def _update_account_last_activity(tx_dict: Dict[str, Any]) -> None:
    """Track last seen timestamp per account for dormancy detection."""
    ts_raw = tx_dict.get("timestamp", datetime.now(timezone.utc))
    if isinstance(ts_raw, str):
        from dateutil.parser import parse
        ts = parse(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    elif isinstance(ts_raw, datetime):
        ts = ts_raw
    else:
        ts = datetime.now(timezone.utc)

    ds_key = _get_dataset_key(tx_dict)
    last_act = _account_last_activities[ds_key]
    for acct_key in ("source_account_id", "destination_account_id"):
        acct = tx_dict.get(acct_key, "")
        if acct:
            if acct not in last_act or ts > last_act[acct]:
                last_act[acct] = ts


def _add_to_graph(tx_dict: Dict[str, Any]) -> None:
    """Add transaction edge to in-memory NetworkX graph."""
    src = tx_dict.get("source_account_id", "")
    dst = tx_dict.get("destination_account_id", "")
    if src and dst:
        ds_key = _get_dataset_key(tx_dict)
        _graphs[ds_key].add_edge(
            src, dst,
            key=tx_dict.get("id", ""),
            amount=float(tx_dict.get("amount", 0)),
            timestamp=str(tx_dict.get("timestamp", "")),
            tx_id=tx_dict.get("id", ""),
        )
        # Store metadata on nodes for graph tooltips
        for node_id, prefix in [(src, "sender"), (dst, "receiver")]:
            name_key = f"{prefix}_name"
            bank_key = f"source_bank_name" if prefix == "sender" else f"destination_bank_name"
            type_key = f"{prefix}_type"
            
            if name_key in tx_dict:
                _graphs[ds_key].nodes[node_id]["owner_name"] = tx_dict[name_key]
            if bank_key in tx_dict:
                _graphs[ds_key].nodes[node_id]["bank_name"] = tx_dict[bank_key]
            if type_key in tx_dict:
                _graphs[ds_key].nodes[node_id]["owner_type"] = tx_dict[type_key]


def _get_recent_txs(ref_ts: Optional[datetime] = None, hours: int = 24, dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return transactions from the last N hours for feature computation."""
    from datetime import timedelta
    if ref_ts is None:
        ref_ts = datetime.now(timezone.utc)
    elif ref_ts.tzinfo is None:
        ref_ts = ref_ts.replace(tzinfo=timezone.utc)
    cutoff = ref_ts - timedelta(hours=hours)

    ds_key = dataset_id or "SYNTHETIC"
    history = _transaction_histories[ds_key]

    result = []
    for t in history:
        ts_raw = t.get("timestamp", datetime.now(timezone.utc))
        if isinstance(ts_raw, str):
            from dateutil.parser import parse
            ts = parse(ts_raw)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if cutoff <= ts <= ref_ts:
            result.append(t)
    return result


def get_graph(dataset_id: Optional[str] = None) -> nx.MultiDiGraph:
    """Return the current in-memory graph."""
    if dataset_id:
        return _graphs[dataset_id]
    combined = nx.MultiDiGraph()
    for g in _graphs.values():
        combined.add_edges_from(g.edges(data=True))
        for node, attrs in g.nodes(data=True):
            combined.add_node(node, **attrs)
    return combined


def get_transaction_history(dataset_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if dataset_id:
        return list(_transaction_histories[dataset_id])
    combined = []
    for hist in _transaction_histories.values():
        combined.extend(hist)
    def _parse_sort_ts(t):
        ts = t.get("timestamp")
        if isinstance(ts, str):
            from dateutil.parser import parse
            return parse(ts)
        return ts or datetime.min
    try:
        combined.sort(key=_parse_sort_ts)
    except Exception:
        pass
    return combined


def reset_pipeline() -> None:
    """Reset all in-memory state (for testing)."""
    global _graphs, _transaction_histories, _account_last_activities
    _graphs.clear()
    _transaction_histories.clear()
    _account_last_activities.clear()
    risk_fusion.clear_alerts()
    redis_client.reset_local_state()

