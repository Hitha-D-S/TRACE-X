# TRACE-X Hackathon Judge Defense Guide & Q&A

This guide prepares Team BrainBytes to defend **TRACE-X** against technical Q&A from hackathon judges.

---

## 1. Core Architecture & Graph Model

### Q: Why did you choose NetworkX instead of Neo4j/GDS for the graph algorithms?
* **A:** *NetworkX is highly optimized for in-memory graph analytics, making it extremely fast (~12ms) and lightweight for near real-time transaction ingestion. Neo4j is used strictly as a persistent transaction store. This hybrid model prevents heavy GDS plug-in dependencies, simplifies the hackathon demo, and enables high-throughput processing on a single API instance.*

### Q: How does Vis.js handle larger graphs in the browser?
* **A:** *The frontend implements graph bounding and paging. It limits the visual network to the 300 most suspicious transactions/nodes at one time. Vis.js is configured with a physics stabilizer that freezes the rendering once stabilized, preventing high CPU load and rendering delays.*

---

## 2. Machine Learning & Anomaly Detection

### Q: How do you prevent data leakage in the Isolation Forest?
* **A:** *We enforce a strict chronological rolling feature builder. When transaction $T_n$ is being evaluated, its feature vector is calculated using historical statistics from transactions $T_0$ to $T_{n-1}$ only. The model does not see future events, ensuring zero target leakage.*

### Q: Why Isolation Forest instead of supervised classifiers?
* **A:** *Financial crime typologies evolve rapidly, and labeled historical fraud datasets are extremely imbalanced or unavailable. Isolation Forest is an unsupervised anomaly detector that specializes in identifying "unknown unknowns" by finding transactions that stand out from the normal behavioral baseline.*

---

## 3. Explanations & Risk Fusion

### Q: How does your risk fusion compounding formula work?
* **A:** *If multiple AML rules trigger, the final risk score compounds using a diminishing return bonus: $\max(\text{scores}) + 0.05 \times (\text{number of rules} - 1)$, capped at 1.0. This prevents multiple minor rule hits from falsely inflating scores, while still representing the compounding danger of multi-signal alerts.*

### Q: How does the counterfactual (What-If) simulator operate?
* **A:** *When an investigator excludes a suspect node, TRACE-X creates a virtual copy of the active subgraph, removes the node, and instantly recalculates PageRank, betweenness centrality, and simple cycles. This allows analysts to quantify how much of the suspicious flow is disrupted by deactivating that specific entity.*

---

## 4. Privacy & Compliance

### Q: How does TRACE-X protect sensitive beneficial ownership data?
* **A:** *We enforce a Zero-Knowledge Identity Policy. All private identifiers (PAN, phone, email) are obfuscated at ingestion. The downstream AI model and external APIs (Gemini) receive only masked values (e.g. `****1234`) and statistical indices, preventing PII leaks.*
