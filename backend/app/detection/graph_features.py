"""
TRACE-X Graph Feature Engine
Computes NetworkX graph metrics for risk scoring.
Uses NetworkX in-memory for offline calculations, bounded by max_depth.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


def build_graph(transactions: List[Dict[str, Any]]) -> nx.MultiDiGraph:
    """Build a directed multigraph from a list of transaction dicts."""
    G = nx.MultiDiGraph()
    for tx in transactions:
        src = tx.get("source_account_id", "")
        dst = tx.get("destination_account_id", "")
        if not src or not dst:
            continue
        G.add_edge(
            src, dst,
            key=tx.get("id", ""),
            amount=float(tx.get("amount", 0)),
            timestamp=str(tx.get("timestamp", "")),
            tx_id=tx.get("id", ""),
            risk=float(tx.get("final_risk_score", 0)),
        )
    return G


class GraphFeatures:
    """Computed graph metrics for a single node."""
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.in_degree: int = 0
        self.out_degree: int = 0
        self.weighted_in_degree: float = 0.0
        self.weighted_out_degree: float = 0.0
        self.pagerank: float = 0.0
        self.betweenness: float = 0.0
        self.component_size: int = 0
        self.cycle_count: int = 0
        self.fan_in_ratio: float = 0.0
        self.fan_out_ratio: float = 0.0
        self.flow_through_ratio: float = 0.0  # (in - out) / (in + out)
        self.shared_identifier_count: int = 0

    def to_dict(self) -> Dict[str, float]:
        return {
            "in_degree": float(self.in_degree),
            "out_degree": float(self.out_degree),
            "weighted_in_degree": self.weighted_in_degree,
            "weighted_out_degree": self.weighted_out_degree,
            "pagerank": self.pagerank,
            "betweenness": self.betweenness,
            "component_size": float(self.component_size),
            "cycle_count": float(self.cycle_count),
            "fan_in_ratio": self.fan_in_ratio,
            "fan_out_ratio": self.fan_out_ratio,
            "flow_through_ratio": self.flow_through_ratio,
        }

    @property
    def risk_score(self) -> float:
        """Normalized 0–1 graph risk score."""
        score = (
            0.25 * min(self.pagerank * 100, 1.0) +
            0.25 * min(self.betweenness * 10, 1.0) +
            0.20 * min(self.cycle_count / 5, 1.0) +
            0.15 * min(self.fan_in_ratio, 1.0) +
            0.15 * abs(self.flow_through_ratio)
        )
        return min(max(score, 0.0), 1.0)


def compute_graph_features(
    G: nx.MultiDiGraph,
    node_id: str,
    max_depth: int = None,
) -> GraphFeatures:
    """Compute graph-level features for a single node."""
    max_depth = max_depth or settings.max_graph_traversal_depth
    feats = GraphFeatures(node_id)

    if node_id not in G:
        return feats

    # Basic degree
    feats.in_degree = G.in_degree(node_id)
    feats.out_degree = G.out_degree(node_id)

    # Weighted degree (by amount)
    feats.weighted_in_degree = sum(
        data.get("amount", 0)
        for _, _, data in G.in_edges(node_id, data=True)
    )
    feats.weighted_out_degree = sum(
        data.get("amount", 0)
        for _, _, data in G.out_edges(node_id, data=True)
    )

    # Flow-through ratio: 0 = balanced, 1 = pure sink/source
    total_flow = feats.weighted_in_degree + feats.weighted_out_degree
    if total_flow > 0:
        feats.flow_through_ratio = abs(
            feats.weighted_in_degree - feats.weighted_out_degree
        ) / total_flow

    # PageRank (on simplified DiGraph)
    simple_G = nx.DiGraph(G)
    try:
        pr = nx.pagerank(simple_G, alpha=0.85, max_iter=100)
        feats.pagerank = pr.get(node_id, 0.0)
    except Exception:
        feats.pagerank = 0.0

    # Betweenness centrality (bounded subgraph)
    try:
        # Extract ego graph for bounded computation
        ego = nx.ego_graph(simple_G, node_id, radius=max_depth, undirected=False)
        bc = nx.betweenness_centrality(ego, normalized=True)
        feats.betweenness = bc.get(node_id, 0.0)
    except Exception:
        feats.betweenness = 0.0

    # Connected component size (undirected view)
    undirected = G.to_undirected()
    if node_id in undirected:
        component = nx.node_connected_component(undirected, node_id)
        feats.component_size = len(component)

    try:
        sub = nx.DiGraph(G)
        all_cycles = []
        for c in nx.simple_cycles(sub):
            all_cycles.append(c)
            if len(all_cycles) >= 100:
                break
        feats.cycle_count = sum(1 for c in all_cycles if node_id in c)
    except Exception:
        feats.cycle_count = 0

    # Fan ratios
    max_in = G.in_degree(node_id)
    max_out = G.out_degree(node_id)
    total_degree = max_in + max_out
    if total_degree > 0:
        feats.fan_in_ratio = max_in / total_degree
        feats.fan_out_ratio = max_out / total_degree

    return feats


def compute_batch_graph_scores(
    transactions: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Compute graph risk score for all accounts in a batch.
    Returns {account_id: score_0_to_1}.
    """
    G = build_graph(transactions)
    scores: Dict[str, float] = {}

    # Compute PageRank once for the full graph
    simple_G = nx.DiGraph(G)
    try:
        pr = nx.pagerank(simple_G, alpha=0.85, max_iter=100)
    except Exception:
        pr = {}

    # Betweenness centrality (only if graph is manageable size)
    try:
        if len(G.nodes) <= 500:
            bc = nx.betweenness_centrality(simple_G, normalized=True)
        else:
            # Sample-based approximation for large graphs
            bc = nx.betweenness_centrality(simple_G, normalized=True, k=min(200, len(G.nodes)))
    except Exception:
        bc = {}

    # Cycle detection (bounded)
    try:
        all_cycles = []
        for c in nx.simple_cycles(simple_G):
            all_cycles.append(c)
            if len(all_cycles) >= 100:
                break
    except Exception:
        all_cycles = []

    cycle_members: Dict[str, int] = defaultdict(int)
    for cycle in all_cycles:
        for node in cycle:
            cycle_members[node] += 1

    for node in G.nodes:
        in_w = sum(d.get("amount", 0) for _, _, d in G.in_edges(node, data=True))
        out_w = sum(d.get("amount", 0) for _, _, d in G.out_edges(node, data=True))
        total = in_w + out_w
        flow_ratio = abs(in_w - out_w) / total if total > 0 else 0.0

        score = (
            0.25 * min(pr.get(node, 0) * 100, 1.0) +
            0.25 * min(bc.get(node, 0) * 10, 1.0) +
            0.20 * min(cycle_members.get(node, 0) / 5, 1.0) +
            0.15 * min(G.in_degree(node) / 20, 1.0) +
            0.15 * flow_ratio
        )
        scores[node] = min(max(score, 0.0), 1.0)

    return scores


def find_suspicious_paths(
    G: nx.MultiDiGraph,
    source: str,
    target: str,
    max_depth: int = None,
) -> List[List[str]]:
    """Find all simple paths between source and target up to max_depth."""
    max_depth = max_depth or settings.max_graph_traversal_depth
    simple_G = nx.DiGraph(G)
    try:
        paths = list(nx.all_simple_paths(simple_G, source, target, cutoff=max_depth))
        return paths[:20]  # cap results
    except Exception:
        return []


def get_cluster_metrics(
    G: nx.MultiDiGraph,
    node_ids: List[str],
) -> Dict[str, Any]:
    """Aggregate cluster-level metrics for a set of nodes."""
    sub = G.subgraph([n for n in node_ids if n in G]).copy()
    simple = nx.DiGraph(sub)

    try:
        cycles = list(nx.simple_cycles(simple))
    except Exception:
        cycles = []

    try:
        pr = nx.pagerank(simple)
        max_pr = max(pr.values()) if pr else 0.0
    except Exception:
        max_pr = 0.0

    total_amount = sum(
        d.get("amount", 0)
        for _, _, d in sub.edges(data=True)
    )

    return {
        "node_count": len(sub.nodes),
        "edge_count": len(sub.edges),
        "cycle_count": len(cycles),
        "max_pagerank": max_pr,
        "total_amount": total_amount,
        "density": nx.density(simple) if len(simple.nodes) > 1 else 0.0,
    }
