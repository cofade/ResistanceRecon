"""Genome Firewall — defensive AI decision-support for antibiotic-response prediction.

Turns a reconstructed Klebsiella pneumoniae genome (FASTA) into a per-antibiotic
verdict (likely to work / likely to fail / no-call) with calibrated confidence and
supporting evidence. Strictly defensive: it analyzes genomes and never designs,
modifies, or optimizes an organism. Every result must be confirmed by standard
laboratory antimicrobial susceptibility testing.

Golden rule: the LLM never predicts. All verdicts and confidence come from the
deterministic per-antibiotic logistic-regression + calibration + conformal pipeline
in ``genome_firewall.predictor``; the ``llm`` package is used only for evidence RAG,
grounded report narration, and review — never as a model input.
"""

__version__ = "0.1.0"
