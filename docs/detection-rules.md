# TRACE-X Detection Rules & Behavioral Models

This document details the rule engine and behavioral anomaly model used to evaluate financial activity.

---

## 1. Deterministic AML Rule Engine

TRACE-X implements **12 deterministic transaction monitoring rules** mapped from actual financial crime patterns. Each detector produces structured evidence details (observed parameters vs. configured thresholds) and computes an explainable sub-score normalized to $[0, 1]$.

### Mapped Typologies & Logic

| Rule ID | Name | Mathematical Logic / Criteria |
|---|---|---|
| **CIRCULAR_FLOW** | Circular Layering | Finds simple cycles in the transaction graph: $A \to B \to C \to A$ with cycle path length $\le \text{max\_depth}$ (default 4). |
| **FUNNEL_ACCOUNT** | Funnel / Mule Account | Identifies accounts with $\ge 3$ inflows (average value $< 30\%$ of outflow) and a single outflow representing $\ge 70\%$ of total inflow value. |
| **RAPID_PASSTHROUGH** | Rapid Pass-Through | Detects incoming transfers routed out within $\le 300\text{ seconds}$ to a third party, where $\text{outflow amount} \approx 98\%\text{ of inflow amount}$. |
| **DORMANT_REACTIVATION** | Dormant Account Reactivation | Triggers when an account inactive for $\ge 90\text{ days}$ suddenly processes a transaction of $\ge \text{Rs. 50,000}$. |
| **STRUCTURING** | Structuring / Splitting | Finds $\ge 3$ transactions just below a reporting threshold (e.g. Rs. 10,000) within a $48\text{-hour}$ sliding window. |
| **TRANSACTION_BURST** | High-Velocity Burst | Triggers when $\ge 10$ transactions originate from a single source within a $3600\text{-second}$ sliding window. |
| **FAN_IN_FAN_OUT** | Fan-In / Fan-Out Hub | Identifies central mixing nodes receiving from $\ge 5$ distinct senders and disbursing to $\ge 5$ distinct receivers within $24\text{ hours}$. |
| **SHARED_METADATA_CLUSTER**| Shared registration clusters | Identifies $\ge 2$ distinct accounts sharing matching director names, PAN, address, phone number, or email registration metadata. |
| **REVENUE_MISMATCH** | Revenue Inconsistency | Flags companies whose transaction volume over $30\text{ days}$ is $\ge 5\text{x}$ their declared average monthly revenue. |
| **ROUND_AMOUNT_PATTERN** | Repeated Round Amounts | Flags accounts making $\ge 3$ large round-number transfers (each $\ge \text{Rs. 10,000}$ and multiple of 1,000) within a $72\text{-hour}$ window. |
| **COUNTERPARTY_CONCENTRATION**| Counterparty Concentration | Flags accounts sending $\ge 80\%$ of their monthly transaction volume to a single receiver (across $\ge 5$ total transactions). |
| **SHORT_CYCLE_DISPERSION** | Short-Cycle Loopback | Triggers when funds flow $A \to B \to C \to A$ (back to neighborhood) within a short window $\le 6\text{ hours}$. |

---

## 2. Behavioral Anomaly Model (Isolation Forest)

Unsupervised machine learning is used to detect novel anomalies that bypass static rules.

### Feature Engineering
For every transaction, a **10-dimensional feature vector** is extracted:
1. `amount`: Raw transaction amount.
2. `amount_log`: Natural log transformation $\ln(\text{amount} + 1)$ to normalize heavy-tailed transaction distributions.
3. `hour_of_day`: Extraction of transaction hour (0-23) to detect nocturnal/irregular timing.
4. `day_of_week`: Day index (0-6) to recognize weekend activity.
5. `is_round_amount`: Binary indicator ($1$ if amount $\ge \text{Rs. 10,000}$ and multiple of 1,000, $0$ otherwise).
6. `src_out_degree`: Out-degree (total transfers sent) of the sender account.
7. `dst_in_degree`: In-degree (total transfers received) of the receiver account.
8. `src_tx_count_24h`: Transaction count of the sender in the last 24 hours.
9. `dst_tx_count_24h`: Transaction count of the receiver in the last 24 hours.
10. `amount_vs_src_mean`: Ratio of the current amount to the historical average transaction amount of the sender.

### Prevention of Future-Information Leakage
Features are calculated using **strictly historical transaction records** prior to the target transaction's timestamp. Future information is never included in the sliding feature windows, preventing leakage and ensuring the model behaves identically during live ingestion as it does on evaluation datasets.

### Model Training
* **Model:** Scikit-Learn `IsolationForest` (100 estimators, 8% contamination rate).
* **Preprocessing:** `StandardScaler` to normalize feature vectors.
* **Auto-Training:** When custom datasets are uploaded, if the dataset size is $\ge 50$ transactions, the pipeline automatically trains a new Isolation Forest instance on the custom dataset baseline and re-initializes the ML scoring, ensuring the model adapts to the specific dataset behavior.
