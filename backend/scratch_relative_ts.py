import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# Add backend directory to Python path
sys.path.insert(0, str(Path(r"C:\Users\Hitha D S\OneDrive\Attachments\omnikon\backend")))

# Reset pipeline
from app.detection.pipeline import reset_pipeline, get_transaction_history
from app.detection import risk_fusion
reset_pipeline()

from app.detection import anomaly
anomaly.load_model()

# Generate dataset
from scripts.generate_synthetic import generate_dataset
dataset = generate_dataset(seed=42, normal_count=200, num_accounts=30)
txs = dataset["transactions"]

# Monkeypatch _get_recent_txs in pipeline
from app.detection import pipeline
from dateutil.parser import parse as parse_dt

def patched_get_recent_txs(ref_ts: datetime, hours: int = 24) -> list:
    cutoff = ref_ts - timedelta(hours=hours)
    result = []
    for t in pipeline._transaction_history:
        ts_raw = t.get("timestamp")
        if isinstance(ts_raw, str):
            ts = parse_dt(ts_raw)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if cutoff <= ts <= ref_ts:
            result.append(t)
    return result

pipeline._get_recent_txs = patched_get_recent_txs

# Also monkeypatch process_transaction to call patched_get_recent_txs with tx timestamp
original_process_transaction = pipeline.process_transaction

async def patched_process_transaction(tx):
    tx_dict = tx.model_dump() if hasattr(tx, "model_dump") else tx
    tx_id = tx_dict["id"]
    t_start = pipeline.time.perf_counter()

    # Track activity
    pipeline._update_account_last_activity(tx_dict)
    pipeline._add_to_graph(tx_dict)
    pipeline._transaction_history.append(tx_dict)

    # 1. Recent transactions relative to current tx timestamp
    from app.detection.rules import _parse_ts
    tx_ts = _parse_ts(tx_dict.get("timestamp", datetime.now(timezone.utc)))
    recent_txs = patched_get_recent_txs(tx_ts, hours=24)

    # 2. Anomaly score
    anomaly_score, top_features_raw = anomaly.score_transaction(tx_dict, pipeline._transaction_history[:-1])
    top_feature_names = [f[0] for f in top_features_raw]

    # 3. Temporal score
    temporal_score = pipeline.temporal_engine.compute_transaction_temporal_score(tx_dict, pipeline._transaction_history)

    # 4. Graph score
    graph_scores = pipeline.graph_engine.compute_batch_graph_scores(recent_txs)
    src_graph = graph_scores.get(tx_dict["source_account_id"], 0.0)
    dst_graph = graph_scores.get(tx_dict["destination_account_id"], 0.0)
    graph_score = max(src_graph, dst_graph)

    # 5. Rule Detection
    from app.detection import rules as rule_engine
    rule_evidences = rule_engine.run_all_rules(
        transactions=recent_txs,
        graph=pipeline._graph,
        entities=[],
        account_last_activity=pipeline._account_last_activity,
    )

    relevant_evidences = [
        e for e in rule_evidences
        if tx_dict["source_account_id"] in e.entity_ids
        or tx_dict["destination_account_id"] in e.entity_ids
        or tx_dict["id"] in e.transaction_ids
    ]

    rule_score = risk_fusion.compute_rule_score(relevant_evidences)

    tx_final_score = round(max(
        (
            pipeline.settings.risk_weight_rule * rule_score +
            pipeline.settings.risk_weight_anomaly * anomaly_score +
            pipeline.settings.risk_weight_graph * graph_score +
            pipeline.settings.risk_weight_temporal * temporal_score
        ),
        rule_score * 0.60
    ) * 100, 2)
    risk_level = pipeline.settings.get_risk_level(tx_final_score)

    from app.models.transaction import TransactionFull
    full_tx = TransactionFull(
        **tx_dict,
        anomaly_score=round(anomaly_score, 4),
        rule_score=round(rule_score, 4),
        temporal_score=round(temporal_score, 4),
        graph_score=round(graph_score, 4),
        final_risk_score=tx_final_score,
        risk_level=risk_level,
    )

    pipeline._transaction_history[-1].update(full_tx.model_dump())

    # Alert Generation
    if relevant_evidences or anomaly_score > 0.65 or tx_final_score >= 60:
        alert_type = risk_fusion.determine_alert_type(relevant_evidences)
        alert = risk_fusion.fuse_risk_scores(
            rule_evidences=relevant_evidences,
            anomaly_score=anomaly_score,
            graph_score=graph_score,
            temporal_score=temporal_score,
            entity_ids=[tx_dict["source_account_id"], tx_dict["destination_account_id"]],
            transaction_ids=[tx_id],
            alert_type=alert_type,
            dataset_id=tx_dict.get("dataset_id", "SYNTHETIC"),
            top_features=top_feature_names,
            model_version=anomaly.get_model_metadata().get("model_version") if anomaly.get_model_metadata() else None,
        )
    return full_tx

pipeline.process_transaction = patched_process_transaction

# Ingest batch
from app.models.transaction import TransactionCreate
import asyncio

async def test_patched():
    create_txs = [TransactionCreate(**t) for t in txs]
    # We use process_batch but it will call our patched process_transaction
    await pipeline.process_batch(create_txs, dataset_id="SYNTHETIC_EVAL")
    
    history = get_transaction_history()
    labeled = [t for t in history if t.get("is_suspicious") is not None]
    
    # Retrieve alerts
    alerts = risk_fusion.list_alerts(limit=10000)
    print(f"\nIngested. Labeled txs: {len(labeled)}. Alerts: {len(alerts)}")
    
    # Check rule scores on suspicious txs
    rule_score_triggers = sum(1 for t in labeled if t.get("rule_score", 0.0) > 0.0)
    print(f"Transactions with rule_score > 0: {rule_score_triggers}")
    
    # Calculate TP, FP, TN, FN if prediction is: tx_id in alerted_tx_ids
    alerted_tx_ids = set()
    for a in alerts:
        alerted_tx_ids.update(a.transaction_ids)
    print(f"Total unique transaction IDs in alerts: {len(alerted_tx_ids)}")
    
    # If predicted is alerted_tx_ids
    tp = fp = fn = tn = 0
    for tx in labeled:
        label = tx.get("is_suspicious", False)
        pred = tx.get("id") in alerted_tx_ids
        if label and pred:
            tp += 1
        elif not label and pred:
            fp += 1
        elif label and not pred:
            fn += 1
        else:
            tn += 1
            
    print("\n=== Prediction: tx_id in alerted_tx_ids ===")
    print(f"TP={tp}, FP={fp}, FN={fn}, TN={tn}")
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / total if total > 0 else 0
    print(f"Precision: {precision*100:.2f}%, Recall: {recall*100:.2f}%, F1: {f1*100:.2f}%, Accuracy: {accuracy*100:.2f}%")

asyncio.run(test_patched())
