# 7. Deployment View

```mermaid
flowchart TB
    subgraph Cloud["Streamlit Community Cloud (demo runtime)"]
        UI["Streamlit UI"] --> API["FastAPI backend"]
        API --> MODELS[("models/ artifacts\n+ demo feature cache")]
        API -->|"key via secrets"| OAI["OpenAI API"]
    end
    subgraph Local["Developer machine — WSL2 (offline)"]
        BV["BV-BRC fetch scripts"] --> DOCK["AMRFinderPlus (ncbi/amr Docker)"]
        DOCK --> TRAIN["train + calibrate + conformal"]
    end
    TRAIN -->|"versioned models + feature cache"| MODELS
```

- **Demo runtime:** pure-Python (Streamlit + FastAPI) on Streamlit Community Cloud; OpenAI key via secrets. **No Docker at demo time** — trained models and a feature cache for the demo genomes ship with the app; the deterministic no-LLM path is the rehearsed fallback.
- **Offline (dev, WSL2):** AMRFinderPlus runs via the pinned `ncbi/amr` Docker image to build the feature matrix and train per-antibiotic models; artifacts are versioned into `models/<drug>/v<N>/`.
- **CI:** no bio-tools, no Docker — `MockAnnotator` + committed fixture TSVs drive the full pipeline. See [ADR-0002](../09-architecture-decisions/ADR-0002-amrfinderplus-via-docker-wsl2.md), [ADR-0007](../09-architecture-decisions/ADR-0007-streamlit-fastapi-demo-stack.md).
