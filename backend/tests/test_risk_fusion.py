"""Tests for risk fusion and normalization."""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from app.detection.risk_fusion import (
    compute_rule_score,
    fuse_risk_scores,
    list_alerts,
    clear_alerts,
)
from app.models.alert import RuleEvidence


def make_evidence(rule_id: str, score: float) -> RuleEvidence:
    return RuleEvidence(
        rule_id=rule_id,
        rule_version="1.0",
        entity_ids=["E1", "E2"],
        transaction_ids=["T1"],
        observed_value={},
        threshold={},
        explanation=f"Test evidence for {rule_id}",
        score=score,
    )


class TestRuleScoreAggregation:
    def test_empty_evidence_gives_zero(self):
        assert compute_rule_score([]) == 0.0

    def test_single_rule_score_preserved(self):
        e = make_evidence("CIRCULAR_FLOW", 0.8)
        score = compute_rule_score([e])
        assert 0.8 <= score <= 1.0  # may have compounding bonus

    def test_multiple_rules_compound(self):
        e1 = make_evidence("CIRCULAR_FLOW", 0.7)
        e2 = make_evidence("FUNNEL_ACCOUNT", 0.6)
        score = compute_rule_score([e1, e2])
        # Multi-flag compounding should push above single-rule score
        assert score >= 0.7
        assert score <= 1.0

    def test_score_bounded_0_to_1(self):
        evidences = [make_evidence(f"RULE_{i}", 0.9) for i in range(10)]
        score = compute_rule_score(evidences)
        assert 0.0 <= score <= 1.0


class TestRiskFusion:
    def setup_method(self):
        clear_alerts()

    def test_zero_scores_produce_low_risk(self):
        alert = fuse_risk_scores(
            rule_evidences=[],
            anomaly_score=0.0,
            graph_score=0.0,
            temporal_score=0.0,
            entity_ids=["E1"],
            transaction_ids=["T1"],
            alert_type="TEST",
        )
        # With all zeros, alert may or may not be generated (depends on threshold)
        if alert:
            assert alert.risk_components.final_risk_score < 30

    def test_high_scores_produce_critical_alert(self):
        clear_alerts()
        e = make_evidence("CIRCULAR_FLOW", 0.95)
        alert = fuse_risk_scores(
            rule_evidences=[e],
            anomaly_score=0.9,
            graph_score=0.85,
            temporal_score=0.8,
            entity_ids=["E1", "E2"],
            transaction_ids=["T1", "T2"],
            alert_type="CIRCULAR_FLOW",
        )
        assert alert is not None
        assert alert.risk_components.final_risk_score >= 60
        assert alert.risk_components.risk_level in ("HIGH", "CRITICAL")

    def test_final_score_bounded_0_to_100(self):
        e = make_evidence("FUNNEL_ACCOUNT", 1.0)
        alert = fuse_risk_scores(
            rule_evidences=[e],
            anomaly_score=1.0,
            graph_score=1.0,
            temporal_score=1.0,
            entity_ids=["E1"],
            transaction_ids=["T1"],
            alert_type="TEST_MAX",
        )
        if alert:
            assert 0.0 <= alert.risk_components.final_risk_score <= 100.0

    def test_risk_level_mapping(self):
        from app.core.config import get_settings
        settings = get_settings()
        assert settings.get_risk_level(15) == "LOW"
        assert settings.get_risk_level(45) == "MEDIUM"
        assert settings.get_risk_level(70) == "HIGH"
        assert settings.get_risk_level(90) == "CRITICAL"

    def test_deduplication_prevents_duplicate_alerts(self):
        clear_alerts()
        e = make_evidence("STRUCTURING", 0.8)
        kwargs = dict(
            rule_evidences=[e],
            anomaly_score=0.5,
            graph_score=0.3,
            temporal_score=0.4,
            entity_ids=["DEDUP-E1", "DEDUP-E2"],
            transaction_ids=["T-DEDUP"],
            alert_type="STRUCTURING",
        )
        alert1 = fuse_risk_scores(**kwargs)
        alert2 = fuse_risk_scores(**kwargs)
        # Both should reference the same alert (dedup)
        if alert1 and alert2:
            assert alert1.id == alert2.id

    def test_alert_has_human_explanation(self):
        e = make_evidence("RAPID_PASSTHROUGH", 0.85)
        alert = fuse_risk_scores(
            rule_evidences=[e],
            anomaly_score=0.7,
            graph_score=0.4,
            temporal_score=0.6,
            entity_ids=["E-EXP"],
            transaction_ids=["T-EXP"],
            alert_type="RAPID_PASSTHROUGH",
        )
        if alert:
            assert len(alert.risk_components.human_explanation) > 20


class TestSafeMetrics:
    """Verify evaluation metric calculations handle zero denominators."""

    def test_precision_zero_denominator(self):
        from app.api.v1.evaluation import _safe_precision
        assert _safe_precision(0, 0) == 0.0

    def test_recall_zero_denominator(self):
        from app.api.v1.evaluation import _safe_recall
        assert _safe_recall(0, 0) == 0.0

    def test_f1_zero_denominator(self):
        from app.api.v1.evaluation import _safe_f1
        assert _safe_f1(0.0, 0.0) == 0.0

    def test_fpr_zero_denominator(self):
        from app.api.v1.evaluation import _safe_fpr
        assert _safe_fpr(0, 0) == 0.0

    def test_precision_correct(self):
        from app.api.v1.evaluation import _safe_precision
        assert abs(_safe_precision(8, 2) - 0.8) < 0.001

    def test_f1_correct(self):
        from app.api.v1.evaluation import _safe_f1
        f1 = _safe_f1(0.8, 0.6)
        assert abs(f1 - (2 * 0.8 * 0.6 / (0.8 + 0.6))) < 0.001
