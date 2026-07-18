# ADR-0007 — Streamlit + FastAPI demo stack

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human.

## Context

Challenge Module 03 requires a working Streamlit or Gradio demo. We also want a clean, reusable API surface and a startup-extensible architecture.

## Decision

Streamlit front end + FastAPI backend. FastAPI exposes `POST /predict`, `GET /health`, `GET /antibiotics`, `GET /model-card`, returning structured `{ok, error}` envelopes (503 on tool failure, never a traceback). Streamlit renders the firewall rule table (ALLOW/BLOCK/REVIEW), per-drug evidence drill-down, calibration/reliability plots, and a non-dismissible lab-confirmation banner on every view. Deploy to Streamlit Community Cloud (OpenAI key via secrets).

## Consequences

- (+) Meets the requirement; clean separation; reusable API; easy one-click deploy.
- (−) Two processes to run/host vs a single Gradio app; the deterministic no-LLM path is rehearsed as the demo fallback.
