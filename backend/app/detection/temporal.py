"""
TRACE-X Temporal Feature Engine
Calculates time-based risk signals from transaction sequences.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple

from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    from dateutil.parser import parse
    dt = parse(str(ts))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TemporalFeatures:
    """Computed temporal features for a single account or transaction."""
    def __init__(self):
        self.burst_score: float = 0.0
        self.relay_score: float = 0.0
        self.velocity: float = 0.0           # transactions per hour
        self.avg_interval_seconds: float = 0.0
        self.dormancy_days: float = 0.0
        self.rolling_amount_mean: float = 0.0
        self.rolling_amount_std: float = 0.0
        self.amount_deviation: float = 0.0   # z-score of latest amount
        self.burst_window_count: int = 0
        self.rapid_relay_count: int = 0
        self.explanation: str = ""

    def to_dict(self) -> Dict[str, float]:
        return {
            "burst_score": self.burst_score,
            "relay_score": self.relay_score,
            "velocity": self.velocity,
            "avg_interval_seconds": self.avg_interval_seconds,
            "dormancy_days": self.dormancy_days,
            "rolling_amount_mean": self.rolling_amount_mean,
            "rolling_amount_std": self.rolling_amount_std,
            "amount_deviation": self.amount_deviation,
            "burst_window_count": float(self.burst_window_count),
            "rapid_relay_count": float(self.rapid_relay_count),
        }

    @property
    def combined_score(self) -> float:
        """Normalized 0–1 temporal risk score."""
        raw = (
            0.35 * self.burst_score +
            0.30 * self.relay_score +
            0.20 * min(self.velocity / 10, 1.0) +
            0.15 * min(self.amount_deviation / 5, 1.0)
        )
        return min(max(raw, 0.0), 1.0)


def compute_temporal_features(
    account_id: str,
    transactions: List[Dict[str, Any]],
    burst_window_seconds: int = 3600,
    burst_threshold: int = 5,
    relay_threshold_seconds: int = 300,
    history_window_days: int = 30,
) -> TemporalFeatures:
    """Compute temporal risk features for a single account."""
    feats = TemporalFeatures()

    # Filter to transactions involving this account
    acct_txs = [
        t for t in transactions
        if t.get("source_account_id") == account_id or
           t.get("destination_account_id") == account_id
    ]
    if not acct_txs:
        return feats

    # Sort by timestamp
    sorted_txs = sorted(acct_txs, key=lambda t: _parse_ts(t.get("timestamp", _now())))
    timestamps = [_parse_ts(t.get("timestamp", _now())) for t in sorted_txs]
    amounts = [float(t.get("amount", 0)) for t in sorted_txs]

    # ── Velocity ──────────────────────────────────────────────
    if len(timestamps) >= 2:
        total_span = (timestamps[-1] - timestamps[0]).total_seconds()
        feats.velocity = len(timestamps) / max(total_span / 3600, 0.001)  # tx/hour

        intervals = [(timestamps[i+1] - timestamps[i]).total_seconds()
                     for i in range(len(timestamps) - 1)]
        feats.avg_interval_seconds = mean(intervals) if intervals else 0.0

    # ── Burst Detection ───────────────────────────────────────
    max_burst = 0
    for i, ts in enumerate(timestamps):
        window_end = ts + timedelta(seconds=burst_window_seconds)
        count = sum(1 for t in timestamps[i:] if t <= window_end)
        max_burst = max(max_burst, count)

    feats.burst_window_count = max_burst
    if max_burst >= burst_threshold:
        feats.burst_score = min(1.0, 0.4 + 0.1 * (max_burst - burst_threshold))

    # ── Rapid Relay (received then immediately sent) ──────────
    received_txs = [t for t in sorted_txs if t.get("destination_account_id") == account_id]
    sent_txs = [t for t in sorted_txs if t.get("source_account_id") == account_id]
    relay_count = 0
    for recv in received_txs:
        recv_ts = _parse_ts(recv.get("timestamp", _now()))
        recv_amt = float(recv.get("amount", 0))
        for sent in sent_txs:
            sent_ts = _parse_ts(sent.get("timestamp", _now()))
            if sent_ts <= recv_ts:
                continue
            if (sent_ts - recv_ts).total_seconds() <= relay_threshold_seconds:
                if abs(float(sent.get("amount", 0)) - recv_amt) / max(recv_amt, 1) <= 0.1:
                    relay_count += 1

    feats.rapid_relay_count = relay_count
    if relay_count > 0:
        feats.relay_score = min(1.0, 0.5 + 0.1 * relay_count)

    # ── Rolling Amount Statistics ─────────────────────────────
    cutoff = _now() - timedelta(days=history_window_days)
    recent_amounts = [
        float(t.get("amount", 0)) for t in sorted_txs
        if _parse_ts(t.get("timestamp", _now())) >= cutoff
    ]
    if recent_amounts:
        feats.rolling_amount_mean = mean(recent_amounts)
        feats.rolling_amount_std = stdev(recent_amounts) if len(recent_amounts) > 1 else 0.0
        if feats.rolling_amount_std > 0 and recent_amounts:
            latest_amount = recent_amounts[-1]
            feats.amount_deviation = abs(latest_amount - feats.rolling_amount_mean) / feats.rolling_amount_std

    # ── Dormancy ──────────────────────────────────────────────
    if len(timestamps) >= 2:
        max_gap = max(
            (timestamps[i+1] - timestamps[i]).total_seconds() / 86400
            for i in range(len(timestamps) - 1)
        )
        feats.dormancy_days = max_gap

    # ── Explanation ───────────────────────────────────────────
    parts = []
    if feats.burst_score > 0:
        parts.append(f"burst={feats.burst_window_count} txs in {burst_window_seconds}s")
    if feats.relay_score > 0:
        parts.append(f"rapid-relay={relay_count} instances")
    if feats.velocity > 5:
        parts.append(f"velocity={feats.velocity:.1f} tx/hr")
    if feats.dormancy_days > 30:
        parts.append(f"dormancy={feats.dormancy_days:.0f} days")
    feats.explanation = "; ".join(parts) if parts else "No notable temporal signals"

    return feats


def compute_batch_temporal_scores(
    transactions: List[Dict[str, Any]],
    burst_window_seconds: int = 3600,
    burst_threshold: int = 5,
) -> Dict[str, float]:
    """
    Compute combined temporal risk score per account for a batch of transactions.
    Returns {account_id: score_0_to_1}.
    """
    accounts: set = set()
    for tx in transactions:
        accounts.add(tx.get("source_account_id", ""))
        accounts.add(tx.get("destination_account_id", ""))
    accounts.discard("")

    scores: Dict[str, float] = {}
    for acct in accounts:
        feats = compute_temporal_features(
            acct, transactions,
            burst_window_seconds=burst_window_seconds,
            burst_threshold=burst_threshold,
        )
        scores[acct] = feats.combined_score

    return scores


def compute_transaction_temporal_score(
    tx: Dict[str, Any],
    all_transactions: List[Dict[str, Any]],
) -> float:
    """
    Per-transaction temporal risk score.
    Uses the source account's temporal features at the time of this transaction.
    """
    src_feats = compute_temporal_features(
        tx["source_account_id"],
        all_transactions,
    )
    dst_feats = compute_temporal_features(
        tx["destination_account_id"],
        all_transactions,
    )
    return max(src_feats.combined_score, dst_feats.combined_score)
