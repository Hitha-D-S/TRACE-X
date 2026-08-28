# TRACE-X Architecture Specification

TRACE-X is a real-time, hybrid financial-crime decision-support system designed to detect, explore, and explain complex layering, money laundering, and shell-company networks.

---

## 1. High-Level Architectural Design

TRACE-X is built on a **microservice-ready, modular architecture** that separates ingestion, transaction enrichment, 5-signal detection scoring, relationship mapping, and AI-grounded triaging.

```
                  ┌───────────────────────────────┐
                  │   CSV/JSON UPLOAD OR STREAM   │
                  └───────────────+───────────────┘
                                  │ HTTP Post / WebSocket Ingestion
                                  ▼
                  ┌───────────────────────────────┐
                  │    FastAPI Ingestion Engine   │
                  └───────────────+───────────────┘
                                  │ Direct Ingest Mode / Redis Buffer
                                  ▼
                  ┌───────────────────────────────┐
                  │  In-Memory NetworkX Multigraph│
                  └───────────────+───────────────┘
                                  │
          ┌───────────────────────+───────────────────────┐
          ▼                       ▼                       ▼
   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
   │ Structural  │         │ Behavioral  │         │ Topological │
   │ Rules (30%) │         │  ML (25%)   │         │  Graph (25%) │
   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
          │                       │                       │
          └───────────────────────+───────────────────────┘
                                  │
                                  ▼
                  ┌───────────────────────────────┐
                  │  Temporal & Entity Engine     │
                  │         (20% Weight)          │
                  └───────────────+───────────────┘
                                  │ Component Scores & Evidence Objects
                                  ▼
                  ┌───────────────────────────────┐
                  │     5-SIGNAL RISK FUSION      │
                  │   Diminishing-Return Bonus    │
                  └───────────────+───────────────┘
                                  │ Alert Payload (Score >= 60)
                                  ▼
                  ┌───────────────────────────────┐
                  │      Alert Lifecycle Store    │
                  │    (PostgreSQL / Memory)      │
                  └──────┬─────────────────┬──────┘
                         │                 │
                         ▼                 ▼
          ┌─────────────────────┐   ┌─────────────────────┐
          │  Command Center UI  │   │ AI Investigation    │
          │  (Next.js / Vis.js) │   │ Assistant (Gemini)  │
          └─────────────────────┘   └─────────────────────┘
```

---

## 2. Ingestion & Data Pipelines

The system is designed with a dual-mode ingestion engine:
* **Direct Ingest (Demo/Local):** Bypasses message brokers for sub-15ms processing latency on lightweight datasets.
* **Buffered Ingest (Production-scale):** Transmits transactions to a Redis-backed queue (`tracex:tx_buffer`) or Apache Kafka/Redpanda cluster before pulling them through asynchronous worker pools.

### In-Memory Graph Processing
For rapid execution during manual triaging, TRACE-X maintains an in-memory `NetworkX` `MultiDiGraph`.
1. Transactions are appended to the graph as directed edges.
2. Nodes represent accounts/entities, containing metadata (e.g. owners, bank associations).
3. The in-memory graph is mirrored to Neo4j asynchronously using non-blocking background tasks (`asyncio.create_task`) to prevent write latency from blocking ingestion.

---

## 3. 5-Signal Fusion Detection Engine

Every transaction is routed through five independent analyzers:
1. **Rule Engine (30%):** Evaluates 12 deterministic AML scenarios (e.g. structuring, dormancy, circular flows).
2. **Behavioral ML (25%):** Predicts anomalous scores via an unsupervised `Isolation Forest` trained on 10 temporal-behavioral features.
3. **Graph Topology (25%):** Measures PageRank and betweenness centrality to identify high-conduit hubs.
4. **Temporal Engine (20%):** Tracks rapid-relay and burst activity (in seconds/minutes).
5. **Entity Linkage:** Resolves shared registrations (PAN, addresses, phone, email) to detect shell company clusters.

Component scores are normalized to $[0, 1]$ and compounded through a diminishing-returns weighted average, creating a composite risk score (0-100).

---

## 4. State Isolation & Security

To prevent data contamination in multi-tenant or multi-dataset investigations:
* **Dataset Isolation:** Every transaction, alert, and graph node is tagged with a `dataset_id`. In-memory filters partition history so that uploaded custom datasets remain strictly isolated from built-in demo datasets.
* **Privacy Safeguards:** A Zero-Knowledge Identity policy masks beneficial owners, PANs, phone numbers, and emails before transmitting evidence packets to downstream LLMs (Gemini), preventing sensitive PII leakage.

---

## 5. Enterprise Scaling Roadmap

While the hackathon prototype runs in-memory with database fallbacks, TRACE-X is architected for enterprise deployment:

| Layer | Prototype Implementation | Production Abstraction |
|---|---|---|
| **Ingestion** | FastAPI endpoints + memory array | Kafka / Redpanda + Spark Streaming |
| **Relational Store**| Memory lists / PostgreSQL fallback | Async SQLAlchemy + PostgreSQL Cluster |
| **Graph Store** | NetworkX `MultiDiGraph` | Neo4j Community / GDS Enterprise |
| **Queue & Cache** | In-memory fallbacks | Redis Sentinel / Cluster |
| **Downstream LLM** | Gemini / Deterministic Fallback | Enterprise API Gateways + VPC Peering |
