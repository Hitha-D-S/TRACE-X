# TRACE-X Submission Demo & Evaluation Workflow

This guide walks through the evaluation and manual triaging workflows of the TRACE-X prototype.

---

## 1. Prerequisites & Installation

Ensure you have Python 3.10+ and Node.js 18+ installed.

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

---

## 2. Running the Platform Locally

### Terminal 1: Start Backend API (runs in-memory demo mode)
```bash
cd backend
.\venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Terminal 2: Start Next.js App
```bash
cd frontend
npm run dev
```
Open your browser at `http://localhost:3000`.

---

## 3. Automated Test Suite

Run the full automated pytest suite:
```bash
cd backend
.\venv\Scripts\python -m pytest tests/ -v
```
All 48 unit and integration tests are verified passing.

---

## 4. Ground-Truth Benchmarks

Run the evaluation script to calculate precision, recall, and confusion matrix:
```bash
cd backend
.\venv\Scripts\python evaluation/evaluate.py --api http://127.0.0.1:8000
```
This script resets the database, generates a labeled synthetic dataset, ingests transactions in batches, and computes overall and per-scenario precision/recall/F1 metrics.

---

## 5. Walkthrough of Investigator Core Features

### 1. Alert Triage Queue
* Load `http://localhost:3000/alerts`.
* Filter alerts by status (`NEW`, `INVESTIGATING`, `RESOLVED`, `FALSE_POSITIVE`) or severity.
* Click an alert to inspect the details panel, which shows the composite risk breakdown, triggered rules, human explanation, and list of entities.
* Assign status changes or append investigator notes.

### 2. Live Network Graph
* Navigate to the **Live Network** page.
* Filter transactions using the minimum risk selector or search for a specific entity ID to center the view.
* Click nodes to view beneficial owner metadata (masked for privacy), banking partner, and transaction volume.

### 3. What-If Sandbox
* Click the **🧪 What-If Analysis** button on any alert details panel.
* Select one or more suspect entity nodes to exclude.
* Click **Run What-If**. The simulated impact appears automatically in the viewport, comparing before vs. after PageRank metrics, transaction flows, and removed cycle counts.
* Click **Restore Original Network** to clear simulation states.

### 4. Chronological Crime Replay
* Click **▶ Replay this alert** to view the timeline of transaction propagation.
* Play, pause, step forward/backward, adjust speed (0.5x to 4x), or scrub the timeline.
* The graph renders only prior transactions up to the scrubbed sequence point.

### 5. Evidence-Grounded AI Brief
* Click **🤖 AI Brief** on an alert panel.
* Read the structured case summary or ask questions in the chat box.
* If a `GEMINI_API_KEY` is not provided in the `.env` file, the engine falls back to the deterministic local Heuristic Analyzer, providing safe local summaries.

### 6. Custom CSV Upload Ingestion
* Navigate to the **Upload Dataset** page.
* Drag and drop a transaction CSV or JSON file.
* TRACE-X auto-maps columns (Source, Destination, Amount, etc.). Confirm or adjust the columns.
* Specify a dataset name and commit.
* The custom dataset is isolated. Navigate back to the Live Network, Alerts, or What-If Sandbox pages and use the **Dataset** dropdown filter to investigate your custom upload without contaminating the built-in demo data.
