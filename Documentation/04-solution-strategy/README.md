# 4. Solution Strategy

| Goal | Strategy |
|---|---|
| Trustworthy verdicts | Two layers: a **deterministic** known-mechanism / molecular-target gate, then a per-antibiotic **calibrated logistic regression**. |
| Honest uncertainty | **Conformal prediction** sets → first-class NO-CALL; calibrated probabilities with reliability + Brier. |
| Honest generalization | **Homology-aware grouped split** (MLST + Mash fallback) with an unseen-lineage holdout. |
| Evidence integrity | `evidence_category` separates a known mechanism from a mere statistical association. |
| Safe LLM use | LLM **structurally barred** from the prediction path (no verdict field; CI import gate). |
| Sustainable build | Six-layer Agentic SE framework; documentation before code. |

```mermaid
flowchart TD
    FASTA([FASTA]) --> ANNO["AMRFinderPlus features"]
    ANNO --> GATE{"Known mechanism\nor target absent?"}
    GATE -- yes --> KM["Deterministic verdict\n(evidence: known_mechanism)"]
    GATE -- no --> LR["Calibrated logistic regression"]
    LR --> CONF{"Conformal set"}
    CONF -->|"{S}"| WORK["LIKELY TO WORK"]
    CONF -->|"{R}"| FAIL["LIKELY TO FAIL"]
    CONF -->|"{S,R} or empty"| NC["NO-CALL"]
    KM --> REPORT["GenomeReport + disclaimer"]
    WORK --> REPORT
    FAIL --> REPORT
    NC --> REPORT
    REPORT -.->|"optional, strictly grounded"| LLMN["LLM narrative + reviewer (fail-closed)"]
```

Related decisions: [ADR-0003](../09-architecture-decisions/ADR-0003-classical-ml-per-antibiotic-logistic-regression.md), [ADR-0004](../09-architecture-decisions/ADR-0004-calibration-and-conformal-prediction-for-no-call.md), [ADR-0005](../09-architecture-decisions/ADR-0005-homology-aware-grouped-split.md), [ADR-0006](../09-architecture-decisions/ADR-0006-llm-boundary-rag-reviewer-report-only.md).
