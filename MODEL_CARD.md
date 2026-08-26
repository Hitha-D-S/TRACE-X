# TRACE-X Model Card

## 1. Model Details
* **Model Name:** TRACE-X Behavioral Anomaly Detector
* **Model Version:** iso-forest-v1.0
* **Model Type:** Isolation Forest (Unsupervised Ensemble Anomaly Detection)
* **Author:** Team BrainBytes (Hitha D S, Chandan D K)
* **Release Date:** August 2026
* **License:** MIT License

## 2. Intended Use
* **Primary Use Case:** Unsupervised behavioral anomaly detection in transaction sequences to identify potential money laundering, tax evasion, shell-company layering, or other financial crimes.
* **Intended Users:** Financial crime compliance officers, AML investigators, and security operations center analysts.
* **Out of Scope:** Automatic freeze/termination of bank accounts or regulatory enforcement without human investigator review. The model acts strictly as a decision-support system.

## 3. Training & Features
The model operates on a **10-feature vector** constructed dynamically from current transaction attributes and rolling historical transactions of both the sender (source) and receiver (destination) accounts:

| Feature Name | Type | Description |
|---|---|---|
| `amount` | Float | Raw transaction amount in local currency (INR). |
| `amount_log` | Float | Natural log transformation of the transaction amount ($\ln(x + 1)$). |
| `hour_of_day` | Float | The hour of day (0-23) the transaction occurred. |
| `day_of_week` | Float | The day of the week (0-6, Monday=0) the transaction occurred. |
| `is_round_amount` | Binary | 1.0 if the amount is a large round number ($\ge 10,000$ and multiple of 1,000), 0.0 otherwise. |
| `src_out_degree` | Float | Total transactions sent by the source account historically (approximate node out-degree). |
| `dst_in_degree` | Float | Total transactions received by the destination account historically (approximate node in-degree). |
| `src_tx_count_24h` | Float | Total transaction velocity of the source account in the last 24 hours. |
| `dst_tx_count_24h` | Float | Total transaction velocity of the destination account in the last 24 hours. |
| `amount_vs_src_mean`| Float | Ratio of the current transaction amount to the historical average transaction amount of the source account. |

## 4. Hyperparameters & Configuration
* **Ensemble Size (`n_estimators`):** 100 trees
* **Contamination Rate:** 8.0% (Assumed base rate of anomaly injection in synthetic datasets)
* **Bootstrap Scaling:** Standard scaler (`StandardScaler`) applied to all features prior to model fit.
* **Feature Leakage Prevention:** Each transaction is scored using features computed only from transactions preceding it chronologically. No future target leakage occurs.

## 5. Metrics & Benchmark Performance
* **Precision:** 70.73% (Ability to avoid false alarms)
* **Recall (Sensitivity):** 86.57% (Ability to detect true suspicious transactions across 8 of 10 typologies at full recall; 2 typologies partially affected by shared account pool reuse in synthetic data)
* **F1 Score:** 77.85%
* **False Positive Rate (FPR):** 12.00%
* **Average Ingestion Latency:** ~12 ms per transaction (measured on local CPU).
