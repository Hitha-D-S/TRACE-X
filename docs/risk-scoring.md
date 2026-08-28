# TRACE-X Risk Scoring & Fusion Engine

TRACE-X maps diverse signals (behavioral, graph topology, temporal sequences, structural rules) into a single, explainable 0–100 risk score.

---

## 1. Sub-Signal Normalization

To ensure equal contribution, each signal analyzer produces a score normalized between $0.0$ and $1.0$:
* **Rule Score ($S_{\text{rule}}$):** Calculated from the maximum score of triggered rules, compounded by a diminishing multi-flag bonus:
  $$S_{\text{rule}} = \min\left(1.0, \max_{r \in R}(S_r) + 0.05 \times (|R| - 1)\right)$$
* **Anomaly Score ($S_{\text{anomaly}}$):** Output anomaly index from the Isolation Forest (rescaled anomaly distance).
* **Graph Score ($S_{\text{graph}}$):** Calculated as the maximum normalized PageRank/centrality score of the source or destination nodes.
* **Temporal Score ($S_{\text{temporal}}$):** Represents transaction burst or relay velocity.

---

## 2. Risk Fusion Formula

The composite risk score is calculated using configured weights from environment variables (defaults: Rule 30%, Anomaly 25%, Graph 25%, Temporal 20%). 
To ensure deterministic rule triggers are not washed out by normal ML/centrality signals, the formula implements a **soft floor** equal to $60\%$ of the aggregated rule score:

$$\text{Raw} = w_{\text{rule}} S_{\text{rule}} + w_{\text{anomaly}} S_{\text{anomaly}} + w_{\text{graph}} S_{\text{graph}} + w_{\text{temporal}} S_{\text{temporal}}$$

$$\text{Final Risk Score (0-100)} = \max\left(\text{Raw}, 0.60 \times S_{\text{rule}}\right) \times 100$$

---

## 3. Risk Severity Levels

The final composite score determines the triage severity:

| Composite Risk Score | Severity Level | UI Badge Color | Action Required |
|---|---|---|---|
| **0 – 29** | **LOW** | Green (`#16a34a`) | Auto-logged; no investigation. |
| **30 – 59** | **MEDIUM** | Yellow (`#ca8a04`) | Standard compliance queue. |
| **60 – 79** | **HIGH** | Orange (`#ea580c`) | Prioritized investigation. |
| **80 – 100** | **CRITICAL** | Red (`#dc2626`) | Immediate review & escalation. |

---

## 4. Evidence Lineage (Explainability)

TRACE-X does not act as a black box. Every composite alert payload exposes an explicit **Evidence Chain** allowing compliance investigators to trace back the reason for flagging:
1. **Final Risk Score:** The overall weighted score.
2. **Contributing Signals:** Component scores (Rule, Anomaly, Graph, Temporal).
3. **Triggered Rules:** Rule IDs, scores, and human-readable explanations describing the specific observed indicators.
4. **Transactions:** Exact matching transaction IDs, amounts, and timestamps that contributed to the cycles, bursts, or relays.
5. **Entities:** Senders and receivers connected by the flows.
