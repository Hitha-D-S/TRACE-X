# TRACE-X Threat Model & Privacy Safeguards

This document defines the security architecture, threat vectors (using the **STRIDE** methodology), and privacy safeguards implemented in **TRACE-X**.

## 1. STRIDE Threat Analysis

| Threat Category | Description / Vector | Mitigation Implemented in TRACE-X |
|---|---|---|
| **Spoofing** | Adversary attempts to ingest fake transactions or impersonate compliance officers. | • Strict Bearer JWT token verification required for ingestion endpoints.<br>• Secure cryptographic signatures for API session establishment. |
| **Tampering** | Unauthorized modifications to transaction history or risk flags. | • Idempotency checks via Redis lock keys prevent replay attacks.<br>• Read-only access controls for historical transaction logs. |
| **Repudiation** | Users claiming they did not submit or review a flagged alert. | • Comprehensive JSON Logging audits action, user email, IP, and timestamp.<br>• Non-editable resolution notes appended with cryptographic audit trail. |
| **Information Disclosure**| Unauthorized leakage of sensitive PII (PAN, phone numbers, emails). | • Strict data-masking constraints applied at ingestion and DB layers.<br>• AI assistant operates on fully masked data (no raw identity egress). |
| **Denial of Service** | Flooding ingestion API to bypass transaction monitoring. | • Dynamic Redis-based batch event buffer absorbs traffic spikes.<br>• Non-blocking async background tasks for Neo4j updates prevent thread exhaustion. |
| **Elevation of Privilege**| Unauthorized access to administrative or system configurations. | • Role-Based Access Control (RBAC) separating `admin`, `investigator`, and `reviewer` scopes. |

## 2. Privacy & Data Masking Controls

TRACE-X strictly adheres to the principle of **Zero-Knowledge Identity Exposure** for downstream LLM/AI layers:

* **Account Masking:** Bank account numbers are truncated to last 4 digits internally (`****1234`) and in UI presentation.
* **Metadata Obfuscation:** Phone numbers, email addresses, and tax identifiers (PAN, GSTIN) are generated synthetically and masked before being sent to the AI assistant or loaded onto dashboards.
* **No Raw Identity Exgress:** The prompt sent to the Gemini API contains *only* masked identities and topology metrics. Under no circumstances are raw names, government IDs, or plaintext credentials sent to external servers.

## 3. Compliance Boundaries

* **No Automatic Decision-Making:** TRACE-X is a decision-support platform. It generates alerts and prioritizes case lists, but does *not* automatically freeze accounts, report to regulators, or make legal assertions of guilt.
* **Explainable AML Evidence:** Every alert is accompanied by the exact component score weights, triggered rule versions, and descriptive summaries, allowing investigators to audits the system's reasoning.
