"""
TRACE-X Neo4j Graph Database Client
Manages the graph schema, constraints, indexes, and Cypher queries.
NetworkX is used for expensive offline calculations; Neo4j stores the persistent graph.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_driver: Optional[AsyncDriver] = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            max_connection_pool_size=50,
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def get_session():
    driver = await get_driver()
    async with driver.session(database="neo4j") as session:
        yield session


# ── Schema Initialization ────────────────────────────────────

CONSTRAINTS = [
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Company) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:BankAccount) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Transaction) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Address) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Phone) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Email) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:PAN) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:GSTIN) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT IF NOT EXISTS FOR (n:Alert) REQUIRE n.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS FOR (n:Transaction) ON (n.timestamp)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Transaction) ON (n.dataset_id)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Transaction) ON (n.final_risk_score)",
    "CREATE INDEX IF NOT EXISTS FOR (n:BankAccount) ON (n.masked_number)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Company) ON (n.legal_name)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Person) ON (n.name)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Alert) ON (n.severity)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Alert) ON (n.created_at)",
    "CREATE INDEX IF NOT EXISTS FOR (n:Alert) ON (n.dataset_id)",
]


async def init_schema() -> None:
    """Apply constraints and indexes. Called on application startup."""
    try:
        async with get_session() as session:
            for stmt in CONSTRAINTS:
                await session.run(stmt)
            for stmt in INDEXES:
                await session.run(stmt)
        logger.info("Neo4j schema initialized")
    except ServiceUnavailable as exc:
        logger.warning("Neo4j unavailable during schema init — will retry later", error=str(exc))


# ── Graph Read Helpers ───────────────────────────────────────

async def get_graph_network(
    dataset_id: Optional[str] = None,
    limit: int = 500,
    min_risk: float = 0.0,
) -> Dict[str, Any]:
    """
    Return nodes and edges for the frontend graph visualization.
    Bounded by limit to avoid rendering huge graphs at once.
    """
    dataset_filter = "WHERE t.dataset_id = $dataset_id" if dataset_id else ""
    params: Dict[str, Any] = {"limit": limit, "min_risk": min_risk}
    if dataset_id:
        params["dataset_id"] = dataset_id

    query = f"""
    MATCH (src:BankAccount)-[t:TRANSACTED_WITH]->(dst:BankAccount)
    {dataset_filter}
    WHERE t.final_risk_score >= $min_risk
    RETURN src, t, dst
    ORDER BY t.final_risk_score DESC
    LIMIT $limit
    """
    nodes: Dict[str, Any] = {}
    edges: List[Dict[str, Any]] = []

    try:
        async with get_session() as session:
            result = await session.run(query, **params)
            async for record in result:
                src = dict(record["src"])
                dst = dict(record["dst"])
                tx = dict(record["t"])

                for n in (src, dst):
                    nid = n.get("id")
                    if nid and nid not in nodes:
                        nodes[nid] = {**n, "labels": ["BankAccount"]}

                edges.append({
                    "id": tx.get("id", ""),
                    "from": src.get("id"),
                    "to": dst.get("id"),
                    **{k: v for k, v in tx.items() if k != "id"},
                })
    except Exception as exc:
        logger.error("Neo4j graph query failed", error=str(exc))

    return {"nodes": list(nodes.values()), "edges": edges}


async def upsert_transaction_graph(tx_data: Dict[str, Any]) -> None:
    """Write a transaction and its endpoint accounts to Neo4j."""
    query = """
    MERGE (src:BankAccount {id: $source_account_id})
      ON CREATE SET src.created_at = $timestamp, src.risk_score = 0.0,
                    src.masked_number = $src_masked, src.bank_name = 'Unknown',
                    src.status = 'ACTIVE', src.dataset_id = $dataset_id
    MERGE (dst:BankAccount {id: $destination_account_id})
      ON CREATE SET dst.created_at = $timestamp, dst.risk_score = 0.0,
                    dst.masked_number = $dst_masked, dst.bank_name = 'Unknown',
                    dst.status = 'ACTIVE', dst.dataset_id = $dataset_id
    MERGE (src)-[t:TRANSACTED_WITH {id: $id}]->(dst)
      ON CREATE SET
        t.amount = $amount,
        t.currency = $currency,
        t.timestamp = $timestamp,
        t.transaction_type = $transaction_type,
        t.channel = $channel,
        t.location = $location,
        t.reference = $reference,
        t.status = $status,
        t.anomaly_score = $anomaly_score,
        t.rule_score = $rule_score,
        t.temporal_score = $temporal_score,
        t.graph_score = $graph_score,
        t.final_risk_score = $final_risk_score,
        t.dataset_id = $dataset_id,
        t.source = $source
    """
    params = {
        **tx_data,
        "src_masked": f"****{tx_data['source_account_id'][-4:]}",
        "dst_masked": f"****{tx_data['destination_account_id'][-4:]}",
    }
    try:
        async with get_session() as session:
            await session.run(query, **params)
    except Exception as exc:
        logger.error("Failed to write transaction to Neo4j", tx_id=tx_data.get("id"), error=str(exc))


async def get_entity_relationships(entity_id: str, max_depth: int = 2) -> Dict[str, Any]:
    """Fetch entity neighborhood up to max_depth hops."""
    query = """
    MATCH (center {id: $entity_id})
    CALL apoc.path.subgraphAll(center, {maxLevel: $depth})
    YIELD nodes, relationships
    RETURN nodes, relationships
    LIMIT 1
    """
    try:
        async with get_session() as session:
            result = await session.run(query, entity_id=entity_id, depth=max_depth)
            record = await result.single()
            if not record:
                return {"nodes": [], "edges": []}
            nodes = [dict(n) for n in record["nodes"]]
            edges = [
                {"from": r.start_node.element_id, "to": r.end_node.element_id, "type": r.type, **dict(r)}
                for r in record["relationships"]
            ]
            return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.error("Entity relationship query failed", entity_id=entity_id, error=str(exc))
        # Fallback: simple 1-hop query without APOC
        return await _simple_neighborhood(entity_id)


async def _simple_neighborhood(entity_id: str) -> Dict[str, Any]:
    """APOC-free 1-hop neighborhood fallback."""
    query = """
    MATCH (n {id: $entity_id})-[r]-(neighbor)
    RETURN n, r, neighbor LIMIT 100
    """
    nodes: Dict[str, Any] = {}
    edges: List[Dict[str, Any]] = []
    try:
        async with get_session() as session:
            result = await session.run(query, entity_id=entity_id)
            async for record in result:
                for node in (record["n"], record["neighbor"]):
                    nid = dict(node).get("id")
                    if nid:
                        nodes[nid] = dict(node)
                r = record["r"]
                edges.append({"from": dict(record["n"]).get("id"),
                               "to": dict(record["neighbor"]).get("id"),
                               "type": r.type})
    except Exception as exc:
        logger.error("Fallback neighborhood query failed", error=str(exc))
    return {"nodes": list(nodes.values()), "edges": edges}


async def health_check() -> bool:
    """Returns True if Neo4j is reachable."""
    try:
        async with get_session() as session:
            await session.run("RETURN 1")
        return True
    except Exception:
        return False
