# 1. Introduction and Goals

## What Genome Firewall is

A strictly **defensive** research prototype that turns a reconstructed, quality-checked *Klebsiella pneumoniae* genome (FASTA) into a per-antibiotic verdict — **likely to work / likely to fail / no-call** — with a calibrated confidence score and the supporting genes/mutations. It supports faster, more targeted antibiotic use and earlier resistance tracking. It is decision *support* only; every result must be confirmed by standard lab testing.

## Requirements overview

Input: one assembled FASTA (one species). Output, per antibiotic: verdict + calibrated confidence + evidence category (known resistance mechanism / statistical association / no signal) + a deterministic molecular-target gate. Scope begins *after* isolation, sequencing, and genome reconstruction.

## Quality goals

| # | Goal | Scenario |
|---|---|---|
| 1 | **Calibrated honesty** | Confidence scores match real held-out performance (Brier + reliability); weak/conflicting/novel evidence returns no-call. |
| 2 | **Honest generalization** | Performance reported on a homology-aware grouped split incl. unseen genetic groups; covered/not-covered scope stated. |
| 3 | **Evidence integrity** | Known mechanism is never conflated with a statistical association; SHAP ≠ causation. |
| 4 | **Defensive by construction** | No capability to design, modify, or optimize an organism exists. |
| 5 | **Human oversight** | Every report carries the mandatory lab-confirmation message. |
| 6 | **Sustainable build** | Ships fast while meeting top-tier SE quality gates (the six-layer framework). |

## Stakeholders

| Role | Interest |
|---|---|
| Healthcare / lab professional | Earlier, trustworthy, clearly-bounded decision support |
| Public-health teams | Resistance-spread tracking |
| Hackathon jury | Safe, honest performance; responsible design; demo quality |
| Sebastian Wienhold (author) | Depth-first excellence + a live case study for the Sustainable Agentic SE paper |

See also: [`research-findings/`](research-findings/) for the web-grounded basis of every technical choice.
