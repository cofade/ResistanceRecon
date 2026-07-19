"""Deterministic, pure-Python narrative renderer (no jinja2 -- keeps ``report/`` off the
optional ``api`` extra). One renderer used three ways: the zero-LLM demo safety net, the
fail-closed fallback when the LLM narrative is rejected, and the canonical source of the
drug names / numbers / verdict words the reviewer's deterministic pre-check checks against.

It never softens a NO-CALL into a soft "probably" and always ends with the exact
lab-confirmation disclaimer carried on the report (golden rule #4).
"""

from __future__ import annotations

from genome_firewall.constants import SUPPORTED_ANTIBIOTICS
from genome_firewall.schemas import AntibioticPrediction, GenomeReport, Verdict

_VERDICT_LABEL: dict[Verdict, str] = {
    "likely_to_work": "LIKELY TO WORK",
    "likely_to_fail": "LIKELY TO FAIL",
    "no_call": "NO CALL",
}

_CATEGORY_LABEL = {
    "known_mechanism": "known resistance mechanism",
    "statistical_association": "statistical association (not a confirmed mechanism)",
    "no_signal": "no resistance signal detected",
}


def _order_key(prediction: AntibioticPrediction) -> tuple[int, str]:
    try:
        return (SUPPORTED_ANTIBIOTICS.index(prediction.antibiotic), prediction.antibiotic)
    except ValueError:
        return (len(SUPPORTED_ANTIBIOTICS), prediction.antibiotic)


def _render_row(prediction: AntibioticPrediction) -> str:
    verdict = _VERDICT_LABEL[prediction.verdict]
    confidence_pct = round(prediction.calibrated_confidence * 100)
    category = _CATEGORY_LABEL[prediction.evidence_category]
    line = f"{prediction.antibiotic}: {verdict} (confidence {confidence_pct}%, {category})."
    if prediction.evidence:
        details = "; ".join(item.description for item in prediction.evidence)
        line += f" Evidence: {details}."
    return line


def render_deterministic_narrative(report: GenomeReport) -> str:
    """Render a deterministic, LLM-free narrative for one report."""
    header = f"Genome {report.genome_id} — per-antibiotic decision support."
    rows = [_render_row(p) for p in sorted(report.predictions, key=_order_key)]
    return "\n".join([header, *rows, report.disclaimer])
