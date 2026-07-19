"""Pure, Streamlit-independent render helpers for the demo UI (issue #28).

No ``streamlit`` import here -- ui/app.py is the only module that touches the ``streamlit``
API; everything it needs to decide what to draw is computed here from the frozen
``GenomeReport`` / ``AntibioticPrediction`` the report/ package already validated. This module
renders only report fields; it never infers a verdict of its own (golden rule #1) and never
omits the disclaimer text callers must always display (golden rule #4).
"""

from __future__ import annotations

from dataclasses import dataclass

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.schemas import AntibioticPrediction, EvidenceCategory, GenomeReport, Verdict

#: verdict -> (firewall label, Streamlit markdown color token), per ADR-0007 / issue #28's
#: ALLOW/BLOCK/REVIEW green/red/amber contract. "amber" is Streamlit markdown's "orange" color
#: token -- same semantic, no CSS injection needed (developing-with-streamlit best practice).
_VERDICT_STYLE: dict[Verdict, tuple[str, str]] = {
    "likely_to_work": ("ALLOW", "green"),
    "likely_to_fail": ("BLOCK", "red"),
    "no_call": ("REVIEW", "orange"),
}

#: evidence_category -> a short badge label distinguishing a deterministic gene/mutation hit
#: (KNOWN mechanism) from a model/SHAP signal (STATISTICAL) -- golden rule #3, never conflated.
_EVIDENCE_BADGE: dict[EvidenceCategory, str] = {
    "known_mechanism": "KNOWN MECHANISM",
    "statistical_association": "STATISTICAL SIGNAL",
    "no_signal": "NO SIGNAL",
}


@dataclass(frozen=True)
class FirewallRow:
    """One antibiotic's rendered firewall-table row.

    UI-internal presentation data, not a report/ schema crossing a module boundary (golden
    rule #5 targets cross-package contracts; this dataclass never leaves ui/) -- a plain
    dataclass is deliberate here rather than a Pydantic model.
    """

    antibiotic: str
    label: str
    color: str
    confidence_pct: float
    evidence_badge: str
    target_present: bool | None
    conformal_labels: tuple[str, ...]


def verdict_style(verdict: Verdict) -> tuple[str, str]:
    """(firewall label, color) for one verdict -- the sole place this mapping is defined."""
    return _VERDICT_STYLE[verdict]


def evidence_badge(category: EvidenceCategory) -> str:
    """Short KNOWN-vs-STATISTICAL badge label for one evidence_category."""
    return _EVIDENCE_BADGE[category]


def firewall_rows(report: GenomeReport) -> tuple[FirewallRow, ...]:
    """The full per-antibiotic firewall table, in panel order, from a built report."""
    rows = []
    for prediction in report.predictions:
        label, color = verdict_style(prediction.verdict)
        rows.append(
            FirewallRow(
                antibiotic=prediction.antibiotic,
                label=label,
                color=color,
                confidence_pct=round(prediction.calibrated_confidence * 100, 1),
                evidence_badge=evidence_badge(prediction.evidence_category),
                target_present=prediction.target_present,
                conformal_labels=(
                    prediction.conformal_set.labels if prediction.conformal_set else ()
                ),
            )
        )
    return tuple(rows)


def evidence_lines(prediction: AntibioticPrediction) -> tuple[str, ...]:
    """The evidence drill-down text for one drug: description + traceable source, per item."""
    return tuple(f"{item.description} — {item.source}" for item in prediction.evidence)


def disclaimer_text() -> str:
    """The mandatory lab-confirmation disclaimer (golden rule #4) -- callers must render this
    on every view, non-dismissibly."""
    return LAB_CONFIRMATION_DISCLAIMER
