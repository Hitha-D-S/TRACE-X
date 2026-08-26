"""
TRACE-X Explainable Risk Fusion Engine
Combines rule, anomaly, graph, and temporal signals into a final risk score.
All component scores normalized to [0, 1] before weighted combination.
Final score is on a 0–100 scale.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.alert import Alert, AlertSeverity, RiskComponents, RuleEvidence

logger = get_logger(__name__)
settings = get_settings()

# In-memory store for deduplication and alert accumulation
# In production: use Redis or Postgres for persistence
_alert_store: Dict[str, Alert] = {}


def _deduplicate_key(
    entity_ids: List[str],
    alert_type: str,
    time_bucket_minutes: int = 60,
) -> str:
    """Create a deduplication key for similar alerts in the same time window."""
    sorted_entities = ",".join(sorted(entity_ids))
    now = datetime.now(timezone.utc)
    bucket = (now.hour * 60 + now.minute) // time_bucket_minutes
    return f"{alert_type}:{sorted_entities}:{bucket}"


def compute_rule_score(evidences: List[RuleEvidence]) -> float:
    """Aggregate multiple rule evidence scores into one [0,1] score."""
    if not evidences:
        return 0.0
    # Use max score with diminishing returns for multiple triggers
    max_score = max(e.score for e in evidences)
    bonus = min(0.15, 0.05 * (len(evidences) - 1))  # multi-flag compounding
    return min(1.0, max_score + bonus)


def fuse_risk_scores(
    rule_evidences: List[RuleEvidence],
    anomaly_score: float,
    graph_score: float,
    temporal_score: float,
    entity_ids: List[str],
    transaction_ids: List[str],
    alert_type: str = "MULTI_SIGNAL",
    dataset_id: Optional[str] = None,
    top_features: Optional[List[str]] = None,
    model_version: Optional[str] = None,
) -> Optional[Alert]:
    """
    Compute final risk score from all component signals.
    Returns an Alert if risk is above threshold, else None.

    Formula (configurable weights from settings):
        final = w_rule * rule + w_anomaly * anomaly + w_graph * graph + w_temporal * temporal
    Normalized to 0–100.
    """
    t_start = time.perf_counter()

    rule_score = compute_rule_score(rule_evidences)


    raw = (
        settings.risk_weight_rule * rule_score +
        settings.risk_weight_anomaly * anomaly_score +
        settings.risk_weight_graph * graph_score +
        settings.risk_weight_temporal * temporal_score
    )
    # Use weighted formula as primary. Rule score provides a soft floor
    # at 60% of raw rule score so that low rule scores produce LOW/MEDIUM,
    # and only high rule scores (>0.8) naturally produce HIGH/CRITICAL.
    final_score_100 = round(max(raw, rule_score * 0.60) * 100, 2)
    risk_level = settings.get_risk_level(final_score_100)
    severity = {
        "LOW": AlertSeverity.LOW,
        "MEDIUM": AlertSeverity.MEDIUM,
        "HIGH": AlertSeverity.HIGH,
        "CRITICAL": AlertSeverity.CRITICAL,
    }.get(risk_level, AlertSeverity.MEDIUM)

    # Build contributing signals map
    contributing = {
        "rule": round(rule_score, 4),
        "anomaly": round(anomaly_score, 4),
        "graph": round(graph_score, 4),
        "temporal": round(temporal_score, 4),
    }

    # Human-readable explanation
    triggered_rules = [e.rule_id for e in rule_evidences]
    explanation_parts = []
    if rule_evidences:
        explanation_parts.append(
            f"Rule engine triggered: {', '.join(triggered_rules)}."
        )
    if anomaly_score > 0.5:
        explanation_parts.append(
            f"Behavioral anomaly score {anomaly_score:.2f} indicates unusual activity."
        )
    if graph_score > 0.5:
        explanation_parts.append(
            f"Graph centrality score {graph_score:.2f} suggests a structurally significant node."
        )
    if temporal_score > 0.5:
        explanation_parts.append(
            f"Temporal score {temporal_score:.2f} indicates burst or rapid relay activity."
        )
    explanation_parts.append(
        f"Final risk score: {final_score_100:.1f}/100 ({risk_level}). "
        "This is a potentially suspicious indicator requiring investigator review."
    )
    explanation = " ".join(explanation_parts)

    risk_components = RiskComponents(
        rule_score=round(rule_score, 4),
        anomaly_score=round(anomaly_score, 4),
        graph_score=round(graph_score, 4),
        temporal_score=round(temporal_score, 4),
        final_risk_score=final_score_100,
        risk_level=risk_level,
        top_features=top_features or [],
        model_version=model_version,
        rule_versions={e.rule_id: e.rule_version for e in rule_evidences},
        human_explanation=explanation,
    )

    # Deduplication
    dedup_key = _deduplicate_key(entity_ids, alert_type)
    if dedup_key in _alert_store:
        existing = _alert_store[dedup_key]
        # Update risk score if higher
        if final_score_100 > existing.risk_components.final_risk_score:
            existing.risk_components = risk_components
            existing.triggered_rules = rule_evidences
            existing.contributing_signals = contributing
            existing.updated_at = datetime.now(timezone.utc)
            logger.info("alert_updated", alert_id=existing.id, score=final_score_100)
        
        # Merge transaction IDs and entity IDs
        for tx_id in transaction_ids:
            if tx_id not in existing.transaction_ids:
                existing.transaction_ids.append(tx_id)
        for ent_id in entity_ids:
            if ent_id not in existing.entity_ids:
                existing.entity_ids.append(ent_id)
        return existing

    alert = Alert(
        alert_type=alert_type,
        severity=severity,
        entity_ids=entity_ids,
        transaction_ids=transaction_ids,
        risk_components=risk_components,
        triggered_rules=rule_evidences,
        contributing_signals=contributing,
        evidence={
            "triggered_rules": [e.model_dump() for e in rule_evidences],
            "component_scores": contributing,
        },
        dataset_id=dataset_id or "SYNTHETIC",
        source=dataset_id.split(":")[0] if dataset_id and ":" in dataset_id else "SYNTHETIC",
    )

    _alert_store[dedup_key] = alert
    t_end = time.perf_counter()
    logger.info(
        "alert_generated",
        alert_id=alert.id,
        alert_type=alert_type,
        score=final_score_100,
        severity=severity.value,
        latency_ms=round((t_end - t_start) * 1000, 2),
    )
    return alert


def get_alert_by_id(alert_id: str) -> Optional[Alert]:
    for alert in _alert_store.values():
        if alert.id == alert_id:
            return alert
    return None


def list_alerts(
    dataset_id: Optional[str] = None,
    min_risk: float = 0.0,
    severity: Optional[str] = None,
    limit: int = 50,
) -> List[Alert]:
    alerts = list(_alert_store.values())
    if dataset_id:
        alerts = [a for a in alerts if a.dataset_id == dataset_id]
    if min_risk > 0:
        alerts = [a for a in alerts if a.risk_components.final_risk_score >= min_risk]
    if severity:
        alerts = [a for a in alerts if a.severity.value == severity]
    alerts.sort(key=lambda a: a.risk_components.final_risk_score, reverse=True)
    return alerts[:limit]


def clear_alerts() -> None:
    """Reset alert store (used in tests)."""
    _alert_store.clear()


def determine_alert_type(rule_evidences: List[RuleEvidence]) -> str:
    """Determine alert type from the highest-scoring rule."""
    if not rule_evidences:
        return "BEHAVIORAL_ANOMALY"
    primary = max(rule_evidences, key=lambda e: e.score)
    return primary.rule_id
