"""Evaluation harness: per-antibiotic metrics (balanced accuracy, resistant-recall headline,
F1, AUROC, PR-AUC, Brier, reliability, no-call rate) marginal + per-group + unseen-lineage.

Re-scores the committed models on the homology split's held-out folds (EPIC 7 / issue #29).
The deterministic predictor stays the sole source of every verdict -- this module only
measures it, never imports ``genome_firewall.llm``.
"""

from genome_firewall.eval.runner import evaluate_drug, evaluate_registry
from genome_firewall.eval.schemas import EvalReport

__all__ = ["EvalReport", "evaluate_drug", "evaluate_registry"]
