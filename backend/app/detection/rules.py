"""
TRACE-X Detection Rules Engine
12 deterministic AML pattern detectors.

Each detector receives a NetworkX graph + recent transactions
and returns structured RuleEvidence objects.

NOTE: All thresholds are DEMO values loaded from config.
      They are NOT legal regulatory thresholds.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.alert import RuleEvidence

logger = get_logger(__name__)
settings = get_settings()


# ── Helper ───────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: Any) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    from dateutil.parser import parse
    dt = parse(str(ts))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _get_ref_ts(transactions: List[Dict[str, Any]]) -> datetime:
    if not transactions:
        return _now()
    tx_times = []
    for tx in transactions:
        ts_raw = tx.get("timestamp")
        if ts_raw:
            tx_times.append(_parse_ts(ts_raw))
    return max(tx_times) if tx_times else _now()



def _make_evidence(
    rule_id: str,
    explanation: str,
    score: float,
    entity_ids: List[str],
    transaction_ids: List[str],
    observed: Dict,
    threshold: Dict,
    time_window: Optional[Dict] = None,
) -> RuleEvidence:
    return RuleEvidence(
        rule_id=rule_id,
        rule_version="1.0",
        entity_ids=entity_ids,
        transaction_ids=transaction_ids,
        observed_value=observed,
        threshold=threshold,
        time_window=time_window or {},
        explanation=explanation,
        score=min(max(score, 0.0), 1.0),
    )


# ────────────────────────────────────────────────────────────
# 1. CIRCULAR FLOW DETECTOR
# ────────────────────────────────────────────────────────────

def detect_circular_flow(
    G: nx.MultiDiGraph,
    transactions: List[Dict[str, Any]],
    max_depth: int = None,
) -> List[RuleEvidence]:
    """Detect A→B→C→...→A cycles within the transaction graph."""
    max_depth = max_depth or settings.circular_flow_max_depth
    results: List[RuleEvidence] = []

    # Build a lightweight directed graph from recent transactions
    sub = nx.DiGraph()
    for tx in transactions:
        sub.add_edge(
            tx["source_account_id"],
            tx["destination_account_id"],
            tx_id=tx["id"],
            amount=float(tx.get("amount", 0)),
            timestamp=str(tx.get("timestamp", "")),
        )

    cycles = []
    try:
        for c in nx.simple_cycles(sub):
            cycles.append(c)
            if len(cycles) >= 100:
                break
    except Exception:
        return results

    for cycle in cycles:
        if len(cycle) < 2 or len(cycle) > max_depth:
            continue

        # Collect transaction IDs in the cycle
        cycle_tx_ids: List[str] = []
        total_amount = 0.0
        for i, node in enumerate(cycle):
            next_node = cycle[(i + 1) % len(cycle)]
            edge_data = sub.get_edge_data(node, next_node)
            if edge_data:
                cycle_tx_ids.append(edge_data.get("tx_id", ""))
                total_amount += edge_data.get("amount", 0)

        score = min(0.95, 0.5 + 0.10 * len(cycle))
        results.append(_make_evidence(
            rule_id="CIRCULAR_FLOW",
            explanation=(
                f"Detected a circular fund flow involving {len(cycle)} accounts: "
                f"{' → '.join(cycle)} → {cycle[0]}. "
                f"Total amount cycled: {total_amount:,.2f}. "
                "This pattern may indicate layering of funds. Requires investigation."
            ),
            score=score,
            entity_ids=cycle,
            transaction_ids=[t for t in cycle_tx_ids if t],
            observed={"cycle_length": len(cycle), "total_amount": total_amount, "cycle_path": cycle},
            threshold={"max_cycle_length": max_depth},
        ))

    return results


# ────────────────────────────────────────────────────────────
# 2. FUNNEL ACCOUNT DETECTOR
# ────────────────────────────────────────────────────────────

def detect_funnel_account(
    transactions: List[Dict[str, Any]],
    window_hours: int = 24,
) -> List[RuleEvidence]:
    """
    Many small inflows followed by one large outflow to a single account.
    Funnel ratio = total_in_count / out_count, with large out/small in amounts.
    """
    results: List[RuleEvidence] = []
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(hours=window_hours)

    inflows: Dict[str, List[Dict]] = defaultdict(list)
    outflows: Dict[str, List[Dict]] = defaultdict(list)

    for tx in transactions:
        ts = _parse_ts(tx.get("timestamp", _now()))
        if ts < cutoff:
            continue
        inflows[tx["destination_account_id"]].append(tx)
        outflows[tx["source_account_id"]].append(tx)

    for account_id, in_txs in inflows.items():
        out_txs = outflows.get(account_id, [])
        if len(in_txs) < 3 or len(out_txs) < 1:
            continue

        total_in = sum(float(t.get("amount", 0)) for t in in_txs)
        total_out = sum(float(t.get("amount", 0)) for t in out_txs)
        avg_in = total_in / len(in_txs) if in_txs else 0
        max_out = max(float(t.get("amount", 0)) for t in out_txs)

        # Flag if single large outflow with many small inflows
        if max_out >= total_in * 0.70 and avg_in < max_out * 0.30 and len(in_txs) >= 3:
            ratio = len(in_txs) / max(len(out_txs), 1)
            score = min(0.9, 0.4 + 0.05 * len(in_txs) + 0.1 * (ratio / 10))
            all_tx_ids = [t["id"] for t in in_txs + out_txs]
            results.append(_make_evidence(
                rule_id="FUNNEL_ACCOUNT",
                explanation=(
                    f"Account {account_id[-6:]} received {len(in_txs)} payments "
                    f"(avg {avg_in:,.0f}) and disbursed a single large payment of "
                    f"{max_out:,.0f} — consistent with a funnel/mule account pattern."
                ),
                score=score,
                entity_ids=[account_id],
                transaction_ids=all_tx_ids,
                observed={"in_count": len(in_txs), "out_count": len(out_txs),
                          "total_in": total_in, "max_out": max_out, "avg_in": avg_in},
                threshold={"min_in_count": 3, "out_in_ratio": 0.70},
                time_window={"hours": window_hours},
            ))

    return results


# ────────────────────────────────────────────────────────────
# 3. RAPID PASS-THROUGH DETECTOR
# ────────────────────────────────────────────────────────────

def detect_rapid_passthrough(
    transactions: List[Dict[str, Any]],
    max_seconds: int = None,
    amount_margin: float = 0.05,
) -> List[RuleEvidence]:
    """Funds received and transferred onward within max_seconds (with similar amount)."""
    max_seconds = max_seconds or settings.rapid_passthrough_seconds
    results: List[RuleEvidence] = []

    # Group by account
    received: Dict[str, List[Dict]] = defaultdict(list)
    sent: Dict[str, List[Dict]] = defaultdict(list)
    for tx in transactions:
        received[tx["destination_account_id"]].append(tx)
        sent[tx["source_account_id"]].append(tx)

    for account_id in set(received) & set(sent):
        for in_tx in received[account_id]:
            in_amount = float(in_tx.get("amount", 0))
            in_ts = _parse_ts(in_tx.get("timestamp", _now()))
            for out_tx in sent[account_id]:
                out_amount = float(out_tx.get("amount", 0))
                out_ts = _parse_ts(out_tx.get("timestamp", _now()))
                if out_ts <= in_ts:
                    continue
                elapsed = (out_ts - in_ts).total_seconds()
                if elapsed > max_seconds:
                    continue
                # Check amount similarity (within margin)
                if in_amount > 0 and abs(out_amount - in_amount) / in_amount <= amount_margin:
                    score = min(0.9, 0.6 + (1 - elapsed / max_seconds) * 0.3)
                    results.append(_make_evidence(
                        rule_id="RAPID_PASSTHROUGH",
                        explanation=(
                            f"Account {account_id[-6:]} received {in_amount:,.0f} and "
                            f"forwarded {out_amount:,.0f} within {elapsed:.0f} seconds "
                            f"({elapsed/60:.1f} min). Rapid relay of similar amounts may "
                            "indicate pass-through layering."
                        ),
                        score=score,
                        entity_ids=[account_id, in_tx["source_account_id"],
                                    out_tx["destination_account_id"]],
                        transaction_ids=[in_tx["id"], out_tx["id"]],
                        observed={"elapsed_seconds": elapsed, "in_amount": in_amount,
                                  "out_amount": out_amount},
                        threshold={"max_seconds": max_seconds, "amount_margin": amount_margin},
                    ))

    return results


# ────────────────────────────────────────────────────────────
# 4. DORMANT ACCOUNT REACTIVATION DETECTOR
# ────────────────────────────────────────────────────────────

def detect_dormant_reactivation(
    account_last_activity: Dict[str, datetime],
    transactions: List[Dict[str, Any]],
    dormancy_days: int = None,
    min_amount: float = 50_000,
) -> List[RuleEvidence]:
    """
    An account dormant for dormancy_days suddenly receives/sends a large amount.
    account_last_activity: {account_id: last_transaction_datetime_before_this_batch}
    """
    dormancy_days = dormancy_days or settings.dormancy_threshold_days
    results: List[RuleEvidence] = []
    threshold_delta = timedelta(days=dormancy_days)

    seen: Set[str] = set()
    for tx in transactions:
        for acct_key in ("source_account_id", "destination_account_id"):
            acct = tx[acct_key]
            if acct in seen:
                continue
            last = account_last_activity.get(acct)
            if last is None:
                continue
            tx_ts = _parse_ts(tx.get("timestamp", _now()))
            gap = tx_ts - last
            if gap < threshold_delta:
                continue
            amount = float(tx.get("amount", 0))
            if amount < min_amount:
                continue
            seen.add(acct)
            gap_days = gap.days
            score = min(0.85, 0.45 + 0.003 * gap_days)
            results.append(_make_evidence(
                rule_id="DORMANT_REACTIVATION",
                explanation=(
                    f"Account {acct[-6:]} was inactive for {gap_days} days and then "
                    f"processed a transaction of {amount:,.0f}. "
                    "Sudden reactivation of dormant accounts can indicate account takeover "
                    "or structured layering activity."
                ),
                score=score,
                entity_ids=[acct],
                transaction_ids=[tx["id"]],
                observed={"gap_days": gap_days, "amount": amount},
                threshold={"dormancy_days": dormancy_days, "min_amount": min_amount},
            ))

    return results


# ────────────────────────────────────────────────────────────
# 5. STRUCTURING / TRANSACTION SPLITTING DETECTOR
# ────────────────────────────────────────────────────────────

def detect_structuring(
    transactions: List[Dict[str, Any]],
    threshold: int = None,
    margin_pct: float = 0.15,
    min_count: int = 3,
    window_hours: int = 48,
) -> List[RuleEvidence]:
    """
    Repeated transactions just below a reporting threshold.
    NOTE: threshold is a DEMO configuration value, not a legal requirement.
    """
    threshold = threshold or settings.structuring_threshold
    results: List[RuleEvidence] = []
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(hours=window_hours)
    lower_bound = threshold * (1 - margin_pct)

    # Group by source account
    by_source: Dict[str, List[Dict]] = defaultdict(list)
    for tx in transactions:
        ts = _parse_ts(tx.get("timestamp", _now()))
        if ts < cutoff:
            continue
        amount = float(tx.get("amount", 0))
        if lower_bound <= amount < threshold:
            by_source[tx["source_account_id"]].append(tx)

    for account_id, txs in by_source.items():
        if len(txs) < min_count:
            continue
        total = sum(float(t.get("amount", 0)) for t in txs)
        score = min(0.9, 0.5 + 0.05 * len(txs))
        results.append(_make_evidence(
            rule_id="STRUCTURING",
            explanation=(
                f"Account {account_id[-6:]} made {len(txs)} transactions between "
                f"{lower_bound:,.0f} and {threshold:,.0f} within {window_hours}h. "
                "Repeated amounts just below a threshold can indicate deliberate "
                "structuring to avoid detection. (Demo threshold — not a legal value.)"
            ),
            score=score,
            entity_ids=[account_id],
            transaction_ids=[t["id"] for t in txs],
            observed={"count": len(txs), "total": total,
                      "amounts": [float(t.get("amount", 0)) for t in txs]},
            threshold={"threshold": threshold, "margin_pct": margin_pct, "min_count": min_count},
            time_window={"hours": window_hours},
        ))

    return results


# ────────────────────────────────────────────────────────────
# 6. TRANSACTION BURST DETECTOR
# ────────────────────────────────────────────────────────────

def detect_transaction_burst(
    transactions: List[Dict[str, Any]],
    window_seconds: int = None,
    count_threshold: int = None,
) -> List[RuleEvidence]:
    """Many transactions from one account within a short time window."""
    window_seconds = window_seconds or settings.burst_window_seconds
    count_threshold = count_threshold or settings.burst_count_threshold
    results: List[RuleEvidence] = []

    by_source: Dict[str, List[Dict]] = defaultdict(list)
    for tx in transactions:
        by_source[tx["source_account_id"]].append(tx)

    for account_id, txs in by_source.items():
        sorted_txs = sorted(txs, key=lambda t: _parse_ts(t.get("timestamp", _now())))
        # Sliding window
        for i in range(len(sorted_txs)):
            window = [sorted_txs[i]]
            start_ts = _parse_ts(sorted_txs[i].get("timestamp", _now()))
            for j in range(i + 1, len(sorted_txs)):
                end_ts = _parse_ts(sorted_txs[j].get("timestamp", _now()))
                if (end_ts - start_ts).total_seconds() <= window_seconds:
                    window.append(sorted_txs[j])
                else:
                    break
            if len(window) >= count_threshold:
                total_amt = sum(float(t.get("amount", 0)) for t in window)
                score = min(0.85, 0.4 + 0.04 * len(window))
                results.append(_make_evidence(
                    rule_id="TRANSACTION_BURST",
                    explanation=(
                        f"Account {account_id[-6:]} initiated {len(window)} transactions "
                        f"within {window_seconds}s, totalling {total_amt:,.0f}. "
                        "High-velocity bursts may indicate automated layering."
                    ),
                    score=score,
                    entity_ids=[account_id],
                    transaction_ids=[t["id"] for t in window],
                    observed={"count": len(window), "window_seconds": window_seconds,
                              "total_amount": total_amt},
                    threshold={"count_threshold": count_threshold,
                               "window_seconds": window_seconds},
                ))
                break  # avoid duplicate alerts per account

    return results


# ────────────────────────────────────────────────────────────
# 7. FAN-IN / FAN-OUT DETECTOR
# ────────────────────────────────────────────────────────────

def detect_fan_in_fan_out(
    transactions: List[Dict[str, Any]],
    min_sources: int = 5,
    min_destinations: int = 5,
    window_hours: int = 24,
) -> List[RuleEvidence]:
    """Many sources converge on one account, then disperse to many destinations."""
    results: List[RuleEvidence] = []
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(hours=window_hours)

    in_sources: Dict[str, Set[str]] = defaultdict(set)
    in_txs: Dict[str, List[str]] = defaultdict(list)
    out_dests: Dict[str, Set[str]] = defaultdict(set)
    out_txs: Dict[str, List[str]] = defaultdict(list)

    for tx in transactions:
        ts = _parse_ts(tx.get("timestamp", _now()))
        if ts < cutoff:
            continue
        dst = tx["destination_account_id"]
        src = tx["source_account_id"]
        in_sources[dst].add(src)
        in_txs[dst].append(tx["id"])
        out_dests[src].add(dst)
        out_txs[src].append(tx["id"])

    # Find hub accounts (high fan-in AND fan-out)
    hubs = set(in_sources) & set(out_dests)
    for hub in hubs:
        n_in = len(in_sources[hub])
        n_out = len(out_dests[hub])
        if n_in >= min_sources and n_out >= min_destinations:
            score = min(0.9, 0.5 + 0.05 * min(n_in, n_out))
            all_entities = list(in_sources[hub] | out_dests[hub] | {hub})
            all_tx_ids = list(set(in_txs[hub] + out_txs[hub]))
            results.append(_make_evidence(
                rule_id="FAN_IN_FAN_OUT",
                explanation=(
                    f"Account {hub[-6:]} received funds from {n_in} distinct sources "
                    f"and dispersed to {n_out} distinct destinations within {window_hours}h. "
                    "This hub pattern may indicate a central mixing node."
                ),
                score=score,
                entity_ids=all_entities[:20],  # cap to avoid huge evidence payloads
                transaction_ids=all_tx_ids[:50],
                observed={"fan_in": n_in, "fan_out": n_out},
                threshold={"min_sources": min_sources, "min_destinations": min_destinations},
                time_window={"hours": window_hours},
            ))

    return results


# ────────────────────────────────────────────────────────────
# 8. SHARED METADATA CLUSTER DETECTOR
# ────────────────────────────────────────────────────────────

def detect_shared_metadata_cluster(
    entities: List[Dict[str, Any]],
    min_shared: int = 2,
    transactions: List[Dict[str, Any]] = None,
) -> List[RuleEvidence]:
    """
    Multiple companies/accounts sharing directors, addresses, phones, emails, or PAN.
    entities: list of entity dicts with optional fields: pan, gstin, phone, email,
              address, director_ids, controller_ids.
    """
    results: List[RuleEvidence] = []
    if transactions is None:
        transactions = []

    def _group_by(field: str) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = defaultdict(list)
        for ent in entities:
            val = ent.get(field)
            if val:
                val_str = str(val).strip().lower()
                if val_str:
                    groups[val_str].append(ent["id"])
        return groups

    shared_fields = ["pan", "gstin", "phone", "email", "address"]
    for field in shared_fields:
        groups = _group_by(field)
        for value, ent_ids in groups.items():
            if len(ent_ids) >= min_shared:
                score = min(0.9, 0.5 + 0.1 * len(ent_ids))
                masked_value = value[:3] + "***" + value[-2:] if len(value) > 5 else "***"
                
                # Fetch only transactions that connect these cluster entities
                cluster_txs = [
                    t["id"] for t in transactions
                    if t.get("source_account_id") in ent_ids
                    and t.get("destination_account_id") in ent_ids
                ]
                
                results.append(_make_evidence(
                    rule_id="SHARED_METADATA_CLUSTER",
                    explanation=(
                        f"{len(ent_ids)} entities share the same {field.upper()} "
                        f"({masked_value}). This may indicate a shell company cluster "
                        "with overlapping beneficial ownership."
                    ),
                    score=score,
                    entity_ids=ent_ids,
                    transaction_ids=cluster_txs,
                    observed={"shared_field": field, "entity_count": len(ent_ids),
                              "masked_value": masked_value},
                    threshold={"min_shared": min_shared},
                ))

    return results


# ────────────────────────────────────────────────────────────
# 9. REVENUE MISMATCH DETECTOR
# ────────────────────────────────────────────────────────────

def detect_revenue_mismatch(
    entity: Dict[str, Any],
    transactions: List[Dict[str, Any]],
    ratio_threshold: float = None,
    window_days: int = 30,
) -> List[RuleEvidence]:
    """Transaction flow materially inconsistent with declared annual revenue."""
    ratio_threshold = ratio_threshold or settings.revenue_mismatch_ratio
    results: List[RuleEvidence] = []
    annual_revenue = entity.get("annual_revenue")
    if not annual_revenue or annual_revenue <= 0:
        return results

    monthly_revenue = annual_revenue / 12
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(days=window_days)
    entity_id = entity["id"]

    entity_txs = [
        t for t in transactions
        if (t.get("source_account_id") == entity_id or
            t.get("destination_account_id") == entity_id) and
        _parse_ts(t.get("timestamp", _now())) >= cutoff
    ]
    if not entity_txs:
        return results

    total_flow = sum(float(t.get("amount", 0)) for t in entity_txs)
    ratio = total_flow / monthly_revenue if monthly_revenue > 0 else 0

    if ratio >= ratio_threshold:
        score = min(0.85, 0.3 + 0.1 * math.log1p(ratio))
        results.append(_make_evidence(
            rule_id="REVENUE_MISMATCH",
            explanation=(
                f"Entity {entity_id[-8:]} processed {total_flow:,.0f} in {window_days} days, "
                f"{ratio:.1f}x its implied monthly revenue ({monthly_revenue:,.0f}). "
                "Significant mismatch between declared revenue and transaction volume "
                "may warrant further investigation."
            ),
            score=score,
            entity_ids=[entity_id],
            transaction_ids=[t["id"] for t in entity_txs[:50]],
            observed={"total_flow": total_flow, "monthly_revenue": monthly_revenue,
                      "ratio": ratio, "window_days": window_days},
            threshold={"ratio_threshold": ratio_threshold},
        ))

    return results


# ────────────────────────────────────────────────────────────
# 10. REPEATED ROUND AMOUNTS DETECTOR
# ────────────────────────────────────────────────────────────

def detect_round_amounts(
    transactions: List[Dict[str, Any]],
    round_threshold: float = None,
    min_count: int = 3,
    window_hours: int = 72,
) -> List[RuleEvidence]:
    """Unusually frequent large round-number transfers from the same account."""
    round_threshold = round_threshold or settings.round_amount_threshold
    results: List[RuleEvidence] = []
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(hours=window_hours)

    by_source: Dict[str, List[Dict]] = defaultdict(list)
    for tx in transactions:
        ts = _parse_ts(tx.get("timestamp", _now()))
        if ts < cutoff:
            continue
        amount = float(tx.get("amount", 0))
        if amount >= round_threshold and amount % 1000 == 0:  # large round number
            by_source[tx["source_account_id"]].append(tx)

    for account_id, txs in by_source.items():
        if len(txs) < min_count:
            continue
        total = sum(float(t.get("amount", 0)) for t in txs)
        score = min(0.75, 0.35 + 0.08 * len(txs))
        results.append(_make_evidence(
            rule_id="ROUND_AMOUNT_PATTERN",
            explanation=(
                f"Account {account_id[-6:]} made {len(txs)} large round-number transfers "
                f"(each ≥{round_threshold:,.0f}) within {window_hours}h. "
                "Repeated round amounts may indicate structured or artificial transactions."
            ),
            score=score,
            entity_ids=[account_id],
            transaction_ids=[t["id"] for t in txs],
            observed={"count": len(txs), "total": total,
                      "amounts": [float(t.get("amount", 0)) for t in txs[:10]]},
            threshold={"round_threshold": round_threshold, "min_count": min_count},
            time_window={"hours": window_hours},
        ))

    return results


# ────────────────────────────────────────────────────────────
# 11. COUNTERPARTY CONCENTRATION DETECTOR
# ────────────────────────────────────────────────────────────

def detect_counterparty_concentration(
    transactions: List[Dict[str, Any]],
    concentration_threshold: float = 0.80,
    window_days: int = 30,
    min_transactions: int = 5,
) -> List[RuleEvidence]:
    """One counterparty accounts for an unusually large share of transactions."""
    results: List[RuleEvidence] = []
    ref_ts = _get_ref_ts(transactions)
    cutoff = ref_ts - timedelta(days=window_days)

    by_source: Dict[str, List[Dict]] = defaultdict(list)
    for tx in transactions:
        ts = _parse_ts(tx.get("timestamp", _now()))
        if ts >= cutoff:
            by_source[tx["source_account_id"]].append(tx)

    for account_id, txs in by_source.items():
        if len(txs) < min_transactions:
            continue
        dest_counts: Dict[str, int] = defaultdict(int)
        for tx in txs:
            dest_counts[tx["destination_account_id"]] += 1
        top_dest, top_count = max(dest_counts.items(), key=lambda x: x[1])
        concentration = top_count / len(txs)
        if concentration >= concentration_threshold:
            score = min(0.75, 0.30 + concentration * 0.5)
            results.append(_make_evidence(
                rule_id="COUNTERPARTY_CONCENTRATION",
                explanation=(
                    f"Account {account_id[-6:]} sent {concentration:.0%} of its transactions "
                    f"to a single counterparty {top_dest[-6:]} within {window_days} days. "
                    "Unusually high counterparty concentration may warrant review."
                ),
                score=score,
                entity_ids=[account_id, top_dest],
                transaction_ids=[t["id"] for t in txs if t["destination_account_id"] == top_dest],
                observed={"concentration": concentration, "top_dest": top_dest,
                          "top_count": top_count, "total_txs": len(txs)},
                threshold={"concentration_threshold": concentration_threshold},
                time_window={"days": window_days},
            ))

    return results


# ────────────────────────────────────────────────────────────
# 12. SHORT-CYCLE FUND DISPERSION DETECTOR
# ────────────────────────────────────────────────────────────

def detect_short_cycle_dispersion(
    transactions: List[Dict[str, Any]],
    max_cycle_hours: float = 6.0,
    min_hops: int = 2,
) -> List[RuleEvidence]:
    """
    Funds pass through multiple accounts and return to neighborhood within a short cycle.
    Simplified: detect chains A→B→C where C == A's prior counterparty.
    """
    results: List[RuleEvidence] = []
    sorted_txs = sorted(transactions, key=lambda t: _parse_ts(t.get("timestamp", _now())))

    # Build quick lookup: {account: last_received_from}
    last_sender: Dict[str, Tuple[str, float, str]] = {}  # acct → (sender, amount, tx_id)

    for tx in sorted_txs:
        src = tx["source_account_id"]
        dst = tx["destination_account_id"]
        amount = float(tx.get("amount", 0))
        ts = _parse_ts(tx.get("timestamp", _now()))

        # Check if dst previously received from a sender that was related to src
        if src in last_sender:
            prior_src, prior_amount, prior_tx_id = last_sender[src]
            # If src was dst in a prior step and the times are close
            prior_info = [(t, a, tid) for acct, (t, a, tid) in last_sender.items() if acct == src]
            if prior_info:
                prior_ts_str, _, prior_tid = prior_info[0]
                if isinstance(prior_ts_str, str):
                    pass  # timestamp stored as string already

        last_sender[dst] = (src, amount, tx["id"])

    # Simplified: look for A→B where B immediately sends back to A's sender
    from_map: Dict[str, List[Dict]] = defaultdict(list)
    to_map: Dict[str, List[Dict]] = defaultdict(list)
    for tx in sorted_txs:
        from_map[tx["source_account_id"]].append(tx)
        to_map[tx["destination_account_id"]].append(tx)

    for account_id in set(from_map) & set(to_map):
        in_txs = to_map[account_id]
        out_txs = from_map[account_id]
        for in_tx in in_txs:
            in_ts = _parse_ts(in_tx.get("timestamp", _now()))
            for out_tx in out_txs:
                out_ts = _parse_ts(out_tx.get("timestamp", _now()))
                if out_ts <= in_ts:
                    continue
                elapsed_hours = (out_ts - in_ts).total_seconds() / 3600
                if elapsed_hours > max_cycle_hours:
                    continue
                # Destination of out_tx receives funds from source of in_tx — short loop
                if out_tx["destination_account_id"] == in_tx["source_account_id"]:
                    score = min(0.88, 0.55 + (1 - elapsed_hours / max_cycle_hours) * 0.3)
                    results.append(_make_evidence(
                        rule_id="SHORT_CYCLE_DISPERSION",
                        explanation=(
                            f"Funds flowed {in_tx['source_account_id'][-6:]} → "
                            f"{account_id[-6:]} → {out_tx['destination_account_id'][-6:]} "
                            f"(back to origin) within {elapsed_hours:.1f}h. "
                            "Short-cycle dispersion may indicate rapid layering."
                        ),
                        score=score,
                        entity_ids=[in_tx["source_account_id"], account_id,
                                    out_tx["destination_account_id"]],
                        transaction_ids=[in_tx["id"], out_tx["id"]],
                        observed={"elapsed_hours": elapsed_hours,
                                  "in_amount": float(in_tx.get("amount", 0)),
                                  "out_amount": float(out_tx.get("amount", 0))},
                        threshold={"max_cycle_hours": max_cycle_hours},
                    ))

    return results


# ────────────────────────────────────────────────────────────
# RULE RUNNER — runs all detectors and returns combined results
# ────────────────────────────────────────────────────────────

def run_all_rules(
    transactions: List[Dict[str, Any]],
    graph: Optional[nx.MultiDiGraph] = None,
    entities: Optional[List[Dict]] = None,
    account_last_activity: Optional[Dict[str, datetime]] = None,
) -> List[RuleEvidence]:
    """Run all rule detectors and return combined evidence list."""
    if graph is None:
        graph = nx.MultiDiGraph()
    if entities is None:
        entities = []
    if account_last_activity is None:
        account_last_activity = {}

    all_evidence: List[RuleEvidence] = []

    try:
        all_evidence.extend(detect_circular_flow(graph, transactions))
    except Exception as e:
        logger.warning("circular_flow detector failed", error=str(e))

    try:
        all_evidence.extend(detect_funnel_account(transactions))
    except Exception as e:
        logger.warning("funnel_account detector failed", error=str(e))

    try:
        all_evidence.extend(detect_rapid_passthrough(transactions))
    except Exception as e:
        logger.warning("rapid_passthrough detector failed", error=str(e))

    try:
        all_evidence.extend(detect_dormant_reactivation(account_last_activity, transactions))
    except Exception as e:
        logger.warning("dormant_reactivation detector failed", error=str(e))

    try:
        all_evidence.extend(detect_structuring(transactions))
    except Exception as e:
        logger.warning("structuring detector failed", error=str(e))

    try:
        all_evidence.extend(detect_transaction_burst(transactions))
    except Exception as e:
        logger.warning("transaction_burst detector failed", error=str(e))

    try:
        all_evidence.extend(detect_fan_in_fan_out(transactions))
    except Exception as e:
        logger.warning("fan_in_fan_out detector failed", error=str(e))

    try:
        all_evidence.extend(detect_shared_metadata_cluster(entities, transactions=transactions))
    except Exception as e:
        logger.warning("shared_metadata_cluster detector failed", error=str(e))

    try:
        for ent in entities:
            all_evidence.extend(detect_revenue_mismatch(ent, transactions))
    except Exception as e:
        logger.warning("revenue_mismatch detector failed", error=str(e))

    try:
        all_evidence.extend(detect_round_amounts(transactions))
    except Exception as e:
        logger.warning("round_amounts detector failed", error=str(e))

    try:
        all_evidence.extend(detect_counterparty_concentration(transactions))
    except Exception as e:
        logger.warning("counterparty_concentration detector failed", error=str(e))

    try:
        all_evidence.extend(detect_short_cycle_dispersion(transactions))
    except Exception as e:
        logger.warning("short_cycle_dispersion detector failed", error=str(e))

    logger.info("rules_complete", rule_count=len(all_evidence))
    return all_evidence
