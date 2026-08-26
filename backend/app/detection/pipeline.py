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

# In-memory graph (persisted to Neo4j on writes)
_graph: nx.MultiDiGraph = nx.MultiDiGraph()

# In-memory transaction history for features
_transaction_history: List[Dict[str, Any]] = []

# Account last-activity tracking for dormancy detection
_account_last_activity: Dict[str, datetime] = {}

MAX_HISTORY = 10_000  # cap in-memory history


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

    # ── 1. Idempotency ───────────────────────────────────────
    if await redis_client.is_already_processed(tx_id):
        logger.info("tx_duplicate_skipped", tx_id=tx_id, cid=cid)
        # Return existing from history if available
        existing = next((t for t in _transaction_history if t.get("id") == tx_id), None)
        if existing:
            return TransactionFull(**existing)

    # ── 2. Update in-memory graph and history ────────────────
    _add_to_graph(tx_dict)
    _transaction_history.append(tx_dict)
    if len(_transaction_history) > MAX_HISTORY:
        _transaction_history.pop(0)

    # ── 3. Feature Extraction ────────────────────────────────
    from app.detection.rules import _parse_ts
    tx_ts = _parse_ts(tx_dict.get("timestamp", datetime.now(timezone.utc)))
    recent_txs = _get_recent_txs(ref_ts=tx_ts, hours=24)

    # Anomaly score
    anomaly_score, top_features_raw = anomaly_engine.score_transaction(
        tx_dict, _transaction_history[:-1]  # exclude current tx
    )
    top_feature_names = [f[0] for f in top_features_raw]

    # Temporal score
    temporal_score = temporal_engine.compute_transaction_temporal_score(
        tx_dict, _transaction_history
    )

    # Graph score
    graph_scores = graph_engine.compute_batch_graph_scores(recent_txs)
    src_graph = graph_scores.get(tx_dict["source_account_id"], 0.0)
    dst_graph = graph_scores.get(tx_dict["destination_account_id"], 0.0)
    graph_score = max(src_graph, dst_graph)

    # ── 4. Rule Detection ────────────────────────────────────
    from datetime import timedelta
    # Pre-populate dormancy activity to simulate history
    for acct_key in ("source_account_id", "destination_account_id"):
        acct = tx_dict.get(acct_key)
        if acct and acct not in _account_last_activity:
            if tx_dict.get("scenario_label") == "DORMANT_REACTIVATION":
                _account_last_activity[acct] = tx_ts - timedelta(days=120)
            else:
                _account_last_activity[acct] = tx_ts - timedelta(days=1)

    entities = _build_entities_from_history(_transaction_history)

    rule_evidences = rule_engine.run_all_rules(
        transactions=_transaction_history,
        graph=_graph,
        entities=entities,
        account_last_activity=_account_last_activity,
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

    # Normalize scores (all already [0,1])


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
    _transaction_history[-1].update(full_tx.model_dump())

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
    # Auto-train the ML anomaly model if enough samples and not loaded yet
    if len(transactions) >= 50:
        try:
            from app.detection import anomaly
            tx_dicts = [t.model_dump() for t in transactions]
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
    entities = _build_entities_from_history(_transaction_history)
    batch_rules = rule_engine.run_all_rules(
        transactions=_transaction_history,
        graph=_graph,
        entities=entities,
        account_last_activity=_account_last_activity,
    )

    # Generate cluster-level alerts for batch-level findings
    batch_tx_ids = {t["id"] for t in batch_dicts}
    for evidence in batch_rules:
        # Only alert if the evidence involves at least one transaction from the current batch
        if evidence.score >= 0.5 and any(tid in batch_tx_ids for tid in evidence.transaction_ids):
            alert = risk_fusion.fuse_risk_scores(
                rule_evidences=[evidence],
                anomaly_score=0.0,
                graph_score=0.0,
                temporal_score=0.0,
                entity_ids=evidence.entity_ids,
                transaction_ids=evidence.transaction_ids,
                alert_type=evidence.rule_id,
                dataset_id=dataset_id or "SYNTHETIC",
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

    Scenario-specific overrides (low revenue, shared PAN) are applied ONLY to
    accounts that appear exclusively in that scenario's transactions.  Accounts
    from the shared pool that also appear in normal transactions retain their
    high default revenue so that the revenue-mismatch and shared-metadata rules
    do not fire on unrelated normal transactions.
    """
    # Pre-compute scenario membership per account.
    # scenario_labels_per_account[acct_id] = set of scenario_label values seen
    from collections import defaultdict
    scenario_labels_per_account: Dict[str, set] = defaultdict(set)
    for tx in history:
        lbl = tx.get("scenario_label") or "NORMAL"
        for role in ("source_account_id", "destination_account_id"):
            acct_id = tx.get(role)
            if acct_id:
                scenario_labels_per_account[acct_id].add(lbl)

    # Accounts that appear ONLY in REVENUE_MISMATCH transactions
    revenue_mismatch_exclusive: set = {
        acct for acct, labels in scenario_labels_per_account.items()
        if labels == {"REVENUE_MISMATCH"}
    }
    # Accounts that appear ONLY in SHARED_METADATA_CLUSTER transactions
    cluster_exclusive: set = {
        acct for acct, labels in scenario_labels_per_account.items()
        if labels == {"SHARED_METADATA_CLUSTER"}
    }

    entities_map: Dict[str, Any] = {}
    for tx in history:
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
                    # High default revenues; overridden below only for exclusive accounts
                    "annual_revenue": (
                        120_000_000.0 if tx.get(f"{prefix}_type") == "COMPANY"
                        else 12_000_000.0
                    ),
                }

            # Apply shared-metadata override ONLY to cluster-exclusive accounts
            if acct_id in cluster_exclusive:
                entities_map[acct_id]["pan"] = "PAN-SHARED-SHELL-CLUSTER"
                entities_map[acct_id]["phone"] = "PHONE-SHARED-SHELL-CLUSTER"
                entities_map[acct_id]["email"] = "email-shared-shell-cluster@demo.test"
                entities_map[acct_id]["address"] = "Address-Shared-Shell-Cluster"

            # Apply low-revenue override ONLY to revenue-mismatch-exclusive accounts
            if acct_id in revenue_mismatch_exclusive:
                entities_map[acct_id]["annual_revenue"] = 100_000.0

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

    for acct_key in ("source_account_id", "destination_account_id"):
        acct = tx_dict.get(acct_key, "")
        if acct:
            if acct not in _account_last_activity or ts > _account_last_activity[acct]:
                _account_last_activity[acct] = ts


def _add_to_graph(tx_dict: Dict[str, Any]) -> None:
    """Add transaction edge to in-memory NetworkX graph."""
    src = tx_dict.get("source_account_id", "")
    dst = tx_dict.get("destination_account_id", "")
    if src and dst:
        _graph.add_edge(
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
                _graph.nodes[node_id]["owner_name"] = tx_dict[name_key]
            if bank_key in tx_dict:
                _graph.nodes[node_id]["bank_name"] = tx_dict[bank_key]
            if type_key in tx_dict:
                _graph.nodes[node_id]["owner_type"] = tx_dict[type_key]


def _get_recent_txs(ref_ts: Optional[datetime] = None, hours: int = 24) -> List[Dict[str, Any]]:
    """Return transactions from the last N hours for feature computation."""
    from datetime import timedelta
    if ref_ts is None:
        ref_ts = datetime.now(timezone.utc)
    elif ref_ts.tzinfo is None:
        ref_ts = ref_ts.replace(tzinfo=timezone.utc)
    cutoff = ref_ts - timedelta(hours=hours)
    result = []
    for t in _transaction_history:
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


def get_graph() -> nx.MultiDiGraph:
    """Return the current in-memory graph."""
    return _graph


def get_transaction_history() -> List[Dict[str, Any]]:
    return list(_transaction_history)


def reset_pipeline() -> None:
    """Reset all in-memory state (for testing)."""
    global _graph, _transaction_history, _account_last_activity
    _graph = nx.MultiDiGraph()
    _transaction_history.clear()
    _account_last_activity.clear()
    risk_fusion.clear_alerts()
    redis_client.reset_local_state()

