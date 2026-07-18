"""Module 02 — The Predictor (the star): deterministic gate + per-antibiotic calibrated
logistic regression + conformal prediction -> verdict/confidence.

The SOLE source of every LIKELY-TO-WORK/FAIL/NO-CALL verdict. Must not import
``genome_firewall.llm`` (enforced by scripts/check_import_boundary.py).
"""
