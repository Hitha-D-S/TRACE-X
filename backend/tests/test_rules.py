"""TRACE-X Test Suite — Rule Detectors"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import networkx as nx
from app.detection.rules import (
    detect_circular_flow,
    detect_funnel_account,
    detect_rapid_passthrough,
    detect_dormant_reactivation,
    detect_structuring,
    detect_transaction_burst,
    detect_fan_in_fan_out,
    detect_round_amounts,
    detect_counterparty_concentration,
    run_all_rules,
)


def make_tx(src, dst, amount, offset_minutes=0, tx_id=None):
    ts = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return {
        "id": tx_id or f"TX-{src[:4]}-{dst[:4]}-{int(amount)}",
        "source_account_id": src,
        "destination_account_id": dst,
        "amount": amount,
        "currency": "INR",
        "timestamp": ts,
        "transaction_type": "NEFT",
        "is_suspicious": True,
        "scenario_label": "TEST",
    }


# ── Circular Flow ──────────────────────────────────────────────

class TestCircularFlow:
    def test_detects_simple_cycle(self):
        txs = [
            make_tx("A", "B", 100_000, 60),
            make_tx("B", "C", 95_000, 40),
            make_tx("C", "A", 90_000, 20),
        ]
        G = nx.MultiDiGraph()
        results = detect_circular_flow(G, txs)
        assert len(results) >= 1
        evidence = results[0]
        assert evidence.rule_id == "CIRCULAR_FLOW"
        assert evidence.score > 0.0
        assert "A" in evidence.entity_ids or "B" in evidence.entity_ids

    def test_no_cycle_gives_no_alert(self):
        txs = [
            make_tx("A", "B", 100_000, 60),
            make_tx("B", "C", 95_000, 40),
            # No return edge
        ]
        G = nx.MultiDiGraph()
        results = detect_circular_flow(G, txs)
        assert len(results) == 0

    def test_score_bounded_0_to_1(self):
        txs = [make_tx("X", "Y", 1000), make_tx("Y", "X", 950)]
        G = nx.MultiDiGraph()
        for r in detect_circular_flow(G, txs):
            assert 0.0 <= r.score <= 1.0

    def test_evidence_has_required_fields(self):
        txs = [make_tx("P", "Q", 50_000), make_tx("Q", "P", 49_000)]
        G = nx.MultiDiGraph()
        results = detect_circular_flow(G, txs)
        if results:
            e = results[0]
            assert e.rule_id is not None
            assert e.rule_version is not None
            assert isinstance(e.entity_ids, list)
            assert isinstance(e.explanation, str) and len(e.explanation) > 10


# ── Funnel Account ─────────────────────────────────────────────

class TestFunnelAccount:
    def test_detects_funnel_pattern(self):
        hub = "HUB-001"
        drain = "DRAIN-001"
        txs = [make_tx(f"SRC-{i:03d}", hub, 5_000, 60 - i * 5) for i in range(6)]
        txs.append(make_tx(hub, drain, 28_000, 5))  # large outflow
        results = detect_funnel_account(txs, window_hours=24)
        assert any(r.rule_id == "FUNNEL_ACCOUNT" for r in results)

    def test_single_inflow_not_flagged(self):
        txs = [make_tx("SRC", "HUB", 5_000, 60)]
        results = detect_funnel_account(txs)
        assert len(results) == 0

    def test_insufficient_inflows_not_flagged(self):
        """Only 2 inflows → should not trigger (min=3)."""
        hub = "HUB-002"
        txs = [
            make_tx("S1", hub, 5_000, 60),
            make_tx("S2", hub, 6_000, 50),
            make_tx(hub, "D1", 20_000, 10),
        ]
        results = detect_funnel_account(txs)
        assert len(results) == 0


# ── Rapid Pass-Through ─────────────────────────────────────────

class TestRapidPassthrough:
    def test_detects_rapid_relay(self):
        relay = "RELAY-001"
        txs = [
            make_tx("SRC", relay, 100_000, 10),   # received 10 minutes ago
            make_tx(relay, "DST", 98_000, 5),     # sent 5 minutes ago
        ]
        results = detect_rapid_passthrough(txs, max_seconds=600)
        assert any(r.rule_id == "RAPID_PASSTHROUGH" for r in results)

    def test_slow_passthrough_not_flagged(self):
        relay = "RELAY-002"
        txs = [
            make_tx("SRC", relay, 100_000, 300),  # 5 hours ago
            make_tx(relay, "DST", 98_000, 5),
        ]
        results = detect_rapid_passthrough(txs, max_seconds=600)
        assert len(results) == 0


# ── Dormant Reactivation ───────────────────────────────────────

class TestDormantReactivation:
    def test_detects_dormant_reactivation(self):
        dormant = "DORMANT-001"
        last_active = datetime.now(timezone.utc) - timedelta(days=150)
        txs = [make_tx("SRC", dormant, 500_000, 0)]
        results = detect_dormant_reactivation(
            {dormant: last_active}, txs, dormancy_days=90, min_amount=100_000
        )
        assert any(r.rule_id == "DORMANT_REACTIVATION" for r in results)

    def test_recent_account_not_flagged(self):
        dormant = "ACTIVE-001"
        last_active = datetime.now(timezone.utc) - timedelta(days=10)
        txs = [make_tx("SRC", dormant, 500_000, 0)]
        results = detect_dormant_reactivation(
            {dormant: last_active}, txs, dormancy_days=90
        )
        assert len(results) == 0


# ── Structuring ────────────────────────────────────────────────

class TestStructuring:
    def test_detects_structuring(self):
        src = "STRUCT-SRC"
        txs = [
            make_tx(src, f"DST-{i}", 9_700, 60 - i * 5)
            for i in range(5)
        ]
        results = detect_structuring(txs, threshold=10_000, min_count=3)
        assert any(r.rule_id == "STRUCTURING" for r in results)

    def test_amounts_above_threshold_not_flagged(self):
        src = "LEGIT-SRC"
        txs = [make_tx(src, f"DST-{i}", 15_000, 60 - i * 5) for i in range(5)]
        results = detect_structuring(txs, threshold=10_000)
        assert len(results) == 0


# ── Transaction Burst ──────────────────────────────────────────

class TestTransactionBurst:
    def test_detects_burst(self):
        src = "BURST-SRC"
        # 12 transactions in last 30 minutes (within 1h window)
        txs = [make_tx(src, f"DST-{i}", 5_000, 30 - i * 2) for i in range(12)]
        results = detect_transaction_burst(txs, window_seconds=3600, count_threshold=5)
        assert any(r.rule_id == "TRANSACTION_BURST" for r in results)

    def test_spread_out_transactions_not_flagged(self):
        src = "CALM-SRC"
        # 10 transactions but spread over many hours (more than burst window)
        txs = [make_tx(src, f"DST-{i}", 5_000, i * 100) for i in range(10)]
        results = detect_transaction_burst(txs, window_seconds=3600, count_threshold=10)
        assert len(results) == 0


# ── Fan-In / Fan-Out ───────────────────────────────────────────

class TestFanInFanOut:
    def test_detects_fan_in_fan_out(self):
        hub = "HUB-FANX"
        txs = [make_tx(f"IN-{i}", hub, 10_000, 60 - i) for i in range(6)]
        txs += [make_tx(hub, f"OUT-{i}", 10_000, i) for i in range(6)]
        results = detect_fan_in_fan_out(txs, min_sources=5, min_destinations=5)
        assert any(r.rule_id == "FAN_IN_FAN_OUT" for r in results)


# ── Round Amounts ──────────────────────────────────────────────

class TestRoundAmounts:
    def test_detects_round_amounts(self):
        src = "ROUND-SRC"
        txs = [make_tx(src, f"DST-{i}", 100_000, 60 - i * 5) for i in range(5)]
        results = detect_round_amounts(txs, round_threshold=10_000, min_count=3)
        assert any(r.rule_id == "ROUND_AMOUNT_PATTERN" for r in results)


# ── Risk Score Bounds ──────────────────────────────────────────

class TestScoreBounds:
    def test_all_scores_bounded(self):
        """All detectors must return scores in [0, 1]."""
        txs = [make_tx("A", "B", 5_000, i) for i in range(20)]
        txs += [make_tx("B", "A", 4_900, i + 20) for i in range(3)]
        txs += [make_tx("A", "C", 9_800, i) for i in range(5)]
        G = nx.MultiDiGraph()
        all_evidence = run_all_rules(txs, graph=G)
        for e in all_evidence:
            assert 0.0 <= e.score <= 1.0, f"{e.rule_id} score {e.score} out of bounds"

    def test_evidence_has_explanation(self):
        txs = [make_tx("X", "Y", 5_000, i) for i in range(15)]
        txs += [make_tx("Y", "X", 4_900, i + 15) for i in range(3)]
        G = nx.MultiDiGraph()
        all_evidence = run_all_rules(txs, graph=G)
        for e in all_evidence:
            assert e.explanation, f"{e.rule_id} has empty explanation"
