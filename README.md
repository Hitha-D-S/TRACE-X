# TRACE-X — Real-Time Financial Crime Graph Intelligence

> **TRACE THE MONEY. REVEAL THE NETWORK. EXPOSE THE RISK.**

*Real-time financial crime intelligence through graph, behavioral, temporal, and entity relationship analysis.*

[![Language](https://img.shields.io/badge/Language-Python-blue.svg)](https://www.python.org/)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-green.svg)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js-black.svg)](https://nextjs.org/)
[![Tests](https://img.shields.io/badge/Tests-Pytest%20Passing-brightgreen.svg)](https://pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)](LICENSE)

**Hackathon:** Omnikon National Hackathon 2026  
**Problem Statement:** Omni_FinTech_10 — *Detecting Shell Companies and Suspicious Transactions*  
**Team:** BrainBytes — Hitha D S, Chandan D K  
**Phase:** Phase 2 — Working Prototype Implementation  

---

## 1. Executive Summary

Traditional transaction monitoring systems evaluate events in isolation (e.g. "Is Rs. 5,00,000 unusual for Account A?"). Financial crime syndicates exploit this limitation by distributing illicit funds across multiple shell accounts, proxy directors, and shared hardware networks to stay below static reporting thresholds.

> *"The problem isn't the transaction. It's the network."*

**TRACE-X** reconstructs financial transactions as a dynamic directed multigraph. It combines **5 distinct intelligence signals**—structural graph rules, behavioral machine learning, topological graph analytics, temporal sequence velocity, and shared entity metadata—to score risk across connected subgraphs in real time.

---

## 2. Implementation Matrix

| Module / Component | Status | Technology |
|---|---|---|
| Synthetic Stream Generator | ✅ IMPLEMENTED | Python `requests` + 4 attack scenarios |
| FastAPI REST Engine | ✅ IMPLEMENTED | FastAPI 0.110 + Pydantic v2 |
| In-Memory Graph Engine | ✅ IMPLEMENTED | NetworkX 3.2.1 `MultiDiGraph` |
| Circular Layering Detector | ✅ IMPLEMENTED | NetworkX cycle analysis (`rules.py`) |
| Funnel Account Mule Detector | ✅ IMPLEMENTED | In-degree aggregation analysis (`rules.py`) |
| Rapid Pass-Through Detector | ✅ IMPLEMENTED | Temporal amount-margin matching (`rules.py`) |
| Dormant Reactivation Detector | ✅ IMPLEMENTED | Inactivity gap & value thresholding (`rules.py`) |
| Isolation Forest Anomaly ML | ✅ IMPLEMENTED | `scikit-learn` IsolationForest + StandardScaler |
| Graph Risk Signal Engine | ✅ IMPLEMENTED | Betweenness centrality & flow-through (`graph_risk.py`) |
| Temporal Intelligence Engine | ✅ IMPLEMENTED | Burst, relay, and velocity tracking (`temporal.py`) |
| 5-Signal Risk Fusion Engine | ✅ IMPLEMENTED | Configurable weighted fusion (`pipeline.py`) |
| Alert Lifecycle Management | ✅ IMPLEMENTED | Status workflow (NEW / INVESTIGATING / ESCALATED / RESOLVED) |
| Vis.js Graph Visualization | ✅ IMPLEMENTED | Vis.js Network dynamic rendering (`page.tsx`) |
| Chronological Crime Replay | ✅ IMPLEMENTED | Edge step-through scrubber & playback (`page.tsx`) |
| What-If Counterfactual Sandbox | ✅ IMPLEMENTED | Node removal & risk recalculation (`page.tsx`) |
| AI Investigation Assistant | ✅ IMPLEMENTED | Gemini 1.5 Flash + Local Fallback Template (`ai_brief.py`) |
| Deterministic Demo Scenarios | ✅ IMPLEMENTED | Demo scenario picker & reset API (`demo_scenarios.py`) |
| Ground-Truth Evaluation Suite | ✅ IMPLEMENTED | Labeled synthetic dataset runner (`evaluate.py`) |
| Pipeline Latency Benchmark | ✅ IMPLEMENTED | Real timing measurement (`benchmark.py`) |
| Neo4j Graph Database Driver | 🔵 PLANNED | Configured driver interface (`database.py`) |
| Apache Kafka / Redpanda Stream | 🔵 PLANNED | Architectural event interface (`config.py`) |

---

## 3. Architecture

```
                       ┌───────────────────────────────┐
                       │  SYNTHETIC STREAM / DEMO MODE │
                       └───────────────┬───────────────┘
                                       │ HTTP Event Stream
                                       ▼
                       ┌───────────────────────────────┐
                       │   FastAPI Ingestion Endpoint  │
                       │ (/api/v1/transactions/ingest) │
                       └───────────────┬───────────────┘
                                       │ Normalization & UUID
                                       ▼
                       ┌───────────────────────────────┐
                       │ NetworkX Financial Multigraph │
                       └───────────────┬───────────────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
  ┌──────────────┐              ┌──────────────┐              ┌──────────────┐
  │  Structural  │              │ Behavioral ML│              │  Graph Risk  │
  │ Rules (40%)  │              │ Anomaly(15%) │              │ Signal (25%) │
  └──────┬───────┘              └──────┬───────┘              └──────┬───────┘
         │                             │                             │
         └─────────────────────────────┼─────────────────────────────┘
                                       │
                        ┌──────────────┴──────────────┐
                        │   Temporal & Entity Signals │
                        │      (10% + 10%)            │
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────┐
                        │   5-SIGNAL RISK FUSION      │
                        │ Multi-flag Compounding (1.20)│
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────┐
                        │ Risk Alert Engine (Score≥70)│
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────┐
                        │ AI Investigation Assistant  │
                        │ (Gemini 1.5 / Local Fallback)│
                        └──────────────┬──────────────┘
                                       │
                                       ▼
                        ┌─────────────────────────────┐
                        │ TRACE-X Command Center UI   │
                        └─────────────────────────────┘
```

---

## 4. Key Features & Demonstration Flow

### 1. Real-Time Risk Fusion
Evaluates each transaction event across 5 component signals:
- **Rule Signal (40%):** Structural patterns (Circular Layering, Funnel Accounts, Rapid Pass-Through, Dormant Reactivation).
- **Graph Signal (25%):** Betweenness centrality, degree, flow-through ratio, cycle participation.
- **Behavioral ML Signal (15%):** Isolation Forest trained on a 10-feature vector using only historical data (zero leakage).
- **Temporal Signal (10%):** Burst sequencing (<60s), rapid relay (<30s), dormancy gaps (>30 days).
- **Entity Signal (10%):** Shared PAN, shared GSTIN, shared IP registration markers.

### 2. Interactive Vis.js Financial Graph
- Suspicious cluster highlighting
- Node/Edge detail tooltips
- Node coloring by entity type (ACCOUNT, COMPANY, WALLET, EXCHANGE)
- Critical conduit highlighting

### 3. Chronological Crime Replay
- Step-by-step playback of financial transfers in sequence
- Play / Pause / Step Forward / Step Backward / Scrub controls
- Visual edge pulsing and active node glowing during playback

### 4. What-If Counterfactual Sandbox
- Select any suspect entity node in the graph and click **[Simulate Deactivation]**
- Recalculates remaining cycles, network component fragmentation, and risk reduction
- Displays exact before vs. after metrics

### 5. Evidence-Grounded AI Investigation Brief
- Summarizes alert evidence using Gemini 1.5 Flash (or local fallback template)
- Zero raw identity exposure (transmits flags like `SHARED_IP: YES`)
- Advisory recommendation language ("Consider reviewing...", "Examine...")
- Audit trail showing model, timestamp, and `evidence_snapshot_id`

---

## 5. Repository Structure

```
omnikon/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI endpoints & route definitions
│   │   ├── pipeline.py        # 5-signal risk fusion & transaction processor
│   │   ├── rules.py           # Structural rule detectors with evidence objects
│   │   ├── anomaly_ml.py      # Isolation Forest anomaly engine (no leakage)
│   │   ├── graph_risk.py      # Centrality, cycle & conduit graph analytics
│   │   ├── temporal.py        # Transaction burst, relay & velocity analytics
│   │   ├── ai_brief.py        # Privacy-safe LLM brief generator & fallback
│   │   ├── database.py        # NetworkX graph state & alert status lifecycle
│   │   └── config.py          # Configurable thresholds & weights
│   ├── evaluation/
│   │   ├── evaluate.py        # Ground-truth benchmark evaluation script
│   │   └── results/           # Benchmark evaluation JSON reports
│   ├── benchmarks/
│   │   ├── benchmark.py       # Latency & throughput benchmarking script
│   │   └── results/           # Latency measurement JSON reports
│   ├── scripts/
│   │   ├── demo_scenarios.py  # Deterministic demo scenario transaction sets
│   │   └── generate_stream.py # Real-time transaction stream generator
│   ├── tests/                 # Automated test suite (48 tests passing)
│   └── requirements.txt       # Python dependencies
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx           # TRACE-X Command Center dashboard
│   │   └── globals.css        # Glassmorphism dark theme styling
│   └── package.json           # Next.js dependencies
├── docs/
│   └── JUDGE_QA.md            # Technical Q&A defense guide for hackathon judges
├── MODEL_CARD.md              # ML model technical specification
├── THREAT_MODEL.md             # STRIDE threat model & privacy controls
└── .env.example               # Documented environment variable template
```

---

## 6. Installation & Quickstart

### Prerequisites
- **Python 3.10+**
- **Node.js 18+ & npm**

### Step 1: Backend Setup
```bash
cd backend
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Step 2: Frontend Setup
```bash
cd frontend
npm install
```

### Step 3: Run the Platform

**Terminal 1 — Backend API Server:**
```bash
cd backend
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Next.js Dashboard:**
```bash
cd frontend
npm run dev
```

Open browser at `http://localhost:3000`.

---

## 7. Running Verification & Benchmarks

### Automated Test Suite
```bash
cd backend
.\venv\Scripts\python -m pytest tests/ -v
```

### Ground-Truth Benchmark Evaluation
```bash
cd backend
.\venv\Scripts\python evaluation/evaluate.py
```

### Latency Benchmark
```bash
cd backend
.\venv\Scripts\python benchmarks/benchmark.py --n 100
```

---

## 8. Measured Operational Metrics (No Fabrication)

| Metric | Measured Value | Benchmark Source |
|---|---|---|
| Automated Test Suite | **48 / 48 PASSING** | `pytest tests/` |
| Pipeline Latency (Mean) | **~117 ms** | `benchmarks/benchmark.py` |
| Pipeline Latency (P95) | **~234 ms** | `benchmarks/benchmark.py` |
| Ground-Truth Recall | **86.57%** | `evaluation/evaluate.py` |
| Ground-Truth Precision | **70.73%** | `evaluation/evaluate.py` |
| Ground-Truth F1 Score | **77.85%** | `evaluation/evaluate.py` |

---

## 9. License & Team

**Team BrainBytes:** Hitha D S | Chandan D K  
**Hackathon:** Omnikon National Hackathon 2026  
**License:** MIT License
