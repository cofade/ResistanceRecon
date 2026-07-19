"""Compose gate -> calibrated model -> conformal into per-antibiotic verdicts (issue #22).

The single entry point of Module 02's inference path and the SOLE source of every
LIKELY-TO-WORK/FAIL/NO-CALL verdict (golden rule #1). For each panel drug, in strict order:

1. **Compatibility.** The genome's AMRFinderPlus DB version and feature schema_version must
   match the trained models' contract, or a typed error is raised (fail loud, never silently
   reindex). Novel genes absent from the vocabulary are fine -- dropped as OOV.
2. **Deterministic gate.** A called known resistance mechanism short-circuits the model:
   verdict ``likely_to_fail``, ``evidence_category=known_mechanism``, fixed high confidence,
   ``conformal_set=None``. One-directional -- the gate never forces ``likely_to_work``.
3. **No model / insufficient data.** A drug that failed the min-n gate (or was never trained)
   is an honest ``no_call`` with ``evidence_category=no_signal`` -- recorded, not hidden.
4. **Calibrated model + conformal.** Otherwise the calibrated P(resistant) -> conformal
   prediction set -> verdict via ``schemas.verdict_for_conformal_set``. Per-genome evidence is
   the signed L2-LR coefficients of the genome's PRESENT features: for binary features against
   an all-absent reference this is the exact linear-model Shapley attribution
   (``shap.LinearExplainer``'s closed form), so it is computed directly rather than pulling the
   heavy ``shap`` runtime dependency onto the inference path (a documented adaptation,
   ADR-0004-style). An empty conformal set (both classes rejected) is a novel/OOD ``no_call``
   with ``no_signal``.

Pure and LLM-free -- predictor/ must not import genome_firewall.llm (CI-enforced). The LLM
never sees a genome before this returns; it may only narrate these verdicts downstream.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from genome_firewall.constants import KNOWN_MECHANISM_CONFIDENCE, SUPPORTED_ANTIBIOTICS
from genome_firewall.features.feature_matrix import build_feature_row
from genome_firewall.features.vocabulary import ENGINEERED_SPEC_VERSION
from genome_firewall.predictor.calibration import predict_resistant_proba
from genome_firewall.predictor.conformal import predict_set
from genome_firewall.predictor.errors import (
    AmrfinderDbVersionMismatchError,
    FeatureSchemaMismatchError,
)
from genome_firewall.predictor.model_registry import DrugModel, PredictorRegistry
from genome_firewall.predictor.target_gate import GateEvaluation, evaluate_gate
from genome_firewall.schemas import (
    AntibioticPrediction,
    EvidenceItem,
    GenomeFeatureVector,
    Verdict,
    verdict_for_conformal_set,
)

#: How many per-feature statistical-association citations to attach to a model-based verdict.
_TOP_K_EVIDENCE = 5


def _check_compatibility(vector: GenomeFeatureVector, registry: PredictorRegistry) -> None:
    """Fail loud on an annotation/schema-version mismatch (novel genes are NOT a mismatch)."""
    if (
        registry.amrfinder_db_version is not None
        and vector.amrfinder_db_version != registry.amrfinder_db_version
    ):
        raise AmrfinderDbVersionMismatchError(
            expected=registry.amrfinder_db_version, actual=vector.amrfinder_db_version
        )
    if registry.schema_version is not None and vector.schema_version != registry.schema_version:
        raise FeatureSchemaMismatchError(
            expected=registry.schema_version, actual=vector.schema_version
        )
    # The engineered columns are derived at predict time by THIS code's features.vocabulary, not
    # carried on the vector -- so the mismatch to catch is running-code vs trained-model, which a
    # bumped schema_version need not cover. Compare the running spec version against the model's.
    if (
        registry.engineered_feature_spec_version is not None
        and registry.engineered_feature_spec_version != ENGINEERED_SPEC_VERSION
    ):
        raise FeatureSchemaMismatchError(
            expected=registry.engineered_feature_spec_version, actual=ENGINEERED_SPEC_VERSION
        )


def _gate_prediction(antibiotic: str, gate: GateEvaluation) -> AntibioticPrediction:
    """A fired gate -> a known-mechanism ``likely_to_fail`` row (one-directional)."""
    citations = gate.subclass_citations or tuple(
        f"AMRFinderPlus call: {gene}" for gene in gate.matched_genes
    )
    rule = gate.result.rule
    evidence = tuple(
        EvidenceItem(
            description=f"{gene}: called known resistance mechanism ({rule})",
            source=citation,
            evidence_category="known_mechanism",
        )
        for gene, citation in zip(gate.matched_genes, citations, strict=True)
    )
    return AntibioticPrediction(
        antibiotic=antibiotic,
        verdict="likely_to_fail",
        calibrated_confidence=KNOWN_MECHANISM_CONFIDENCE,
        evidence_category="known_mechanism",
        supporting_features=gate.matched_genes,
        evidence=evidence,
        target_present=gate.target_present,
        conformal_set=None,
    )


def _no_model_prediction(
    antibiotic: str, gate: GateEvaluation, *, reason: str
) -> AntibioticPrediction:
    """A drug with no trained model (insufficient data / never trained) -> honest no_call."""
    return AntibioticPrediction(
        antibiotic=antibiotic,
        verdict="no_call",
        calibrated_confidence=0.0,
        evidence_category="no_signal",
        supporting_features=(),
        evidence=(
            EvidenceItem(
                description=reason,
                source="predictor/model_registry",
                evidence_category="no_signal",
            ),
        ),
        target_present=gate.target_present,
        conformal_set=None,
    )


def _present_contributions(
    row: npt.NDArray[np.float64], drug_model: DrugModel
) -> list[tuple[str, float]]:
    """Present (nonzero) features paired with their signed LR coefficient -- the exact per-genome
    linear attribution (coef*x, x in {0,1}) against an all-absent reference; the sigmoid calibrator
    is a monotone transform of the decision function, so these directional weights explain the
    score the served probability monotonically maps from. The full coefficient vector is persisted
    (train._signed_coefficients), so every present feature has its real weight. Sorted by |weight|.
    """
    coef_by_feature = {c.feature: c.coefficient for c in drug_model.coefficients}
    present = [
        (name, coef_by_feature.get(name, 0.0))
        for name, value in zip(drug_model.feature_schema.feature_names, row, strict=True)
        if value != 0.0
    ]
    present.sort(key=lambda item: (-abs(item[1]), item[0]))
    return present


def _model_evidence(
    row: npt.NDArray[np.float64],
    drug_model: DrugModel,
    *,
    antibiotic: str,
    verdict: Verdict,
    p_resistant: float,
) -> tuple[tuple[str, ...], tuple[EvidenceItem, ...]]:
    """Statistical-association supporting_features + EvidenceItems for a model-based verdict."""
    contributions = _present_contributions(row, drug_model)
    source = (
        f"per-drug L2 logistic regression ({drug_model.version}); "
        f"calibrated p(resistant)={p_resistant:.3f}"
    )
    features: list[str] = []
    evidence: list[EvidenceItem] = []

    # Surface a void conformal guarantee in EVERY affected verdict, never only in the model card:
    # a small calibration set can strip the finite-sample coverage guarantee (guarantee_available
    # reflects calibration-set SIZE, not model quality -- gentamicin is guarantee-void yet strong),
    # so the honest move is to flag it on the verdict, not to silently downgrade a useful model.
    if not drug_model.conformal.guarantee_available:
        caveat = (
            f"conformal finite-sample coverage guarantee UNAVAILABLE for {antibiotic} "
            "(calibration set below the n>=ceil(1/alpha)-1 floor); treat as lower-confidence "
            "and confirm by lab testing"
        )
        features.append(caveat)
        evidence.append(
            EvidenceItem(
                description=caveat, source=source, evidence_category="statistical_association"
            )
        )

    if verdict == "likely_to_fail":
        drivers = [(name, weight) for name, weight in contributions if weight > 0][:_TOP_K_EVIDENCE]
        for name, weight in drivers:
            text = f"{name} (LR weight {weight:+.2f} toward resistance)"
            features.append(text)
            evidence.append(
                EvidenceItem(
                    description=text, source=source, evidence_category="statistical_association"
                )
            )
        summary = f"statistical model estimated resistance (calibrated p={p_resistant:.2f})"
    elif verdict == "likely_to_work":
        protectors = [(name, weight) for name, weight in contributions if weight < 0][
            :_TOP_K_EVIDENCE
        ]
        for name, weight in protectors:
            text = f"{name} (LR weight {weight:+.2f} toward susceptibility)"
            features.append(text)
            evidence.append(
                EvidenceItem(
                    description=text, source=source, evidence_category="statistical_association"
                )
            )
        if not any(weight > 0 for _name, weight in contributions):
            # Defensive honesty: a 'work' call with no resistance determinants says exactly that
            # (the brief's caution against declaring 'works' from mere marker-absence -- here the
            # calibrated model + conformal, not the gate, made the affirmative call).
            note = f"no known {antibiotic}-resistance determinants detected"
            features.append(note)
            evidence.append(
                EvidenceItem(
                    description=note, source=source, evidence_category="statistical_association"
                )
            )
        summary = (
            "statistical model estimated susceptibility "
            f"(calibrated p(resistant)={p_resistant:.2f})"
        )
    else:  # no_call from a non-empty, ambiguous {S,R} conformal set
        summary = (
            f"conformal set ambiguous at alpha={drug_model.alpha}: the model could not separate "
            f"S from R at the configured coverage (calibrated p(resistant)={p_resistant:.2f})"
        )

    features.append(summary)
    evidence.append(
        EvidenceItem(
            description=summary, source=source, evidence_category="statistical_association"
        )
    )
    return tuple(features), tuple(evidence)


def _model_prediction(
    vector: GenomeFeatureVector, drug_model: DrugModel, gate: GateEvaluation
) -> AntibioticPrediction:
    """Calibrated model -> conformal set -> verdict + statistical-association evidence."""
    row, _oov = build_feature_row(vector, drug_model.feature_schema)
    p_resistant = float(predict_resistant_proba(drug_model.calibrated_model, row.reshape(1, -1))[0])
    conformal_set = predict_set(drug_model.conformal, p_resistant)
    verdict = verdict_for_conformal_set(conformal_set.labels)

    if verdict == "no_call" and len(conformal_set.labels) == 0:
        # Empty set: both classes rejected -> novel / out-of-distribution, not a model opinion.
        return AntibioticPrediction(
            antibiotic=drug_model.antibiotic,
            verdict="no_call",
            calibrated_confidence=max(p_resistant, 1.0 - p_resistant),
            evidence_category="no_signal",
            supporting_features=(),
            evidence=(
                EvidenceItem(
                    description=(
                        "novel / out-of-distribution: the conformal procedure admitted neither "
                        f"S nor R at alpha={drug_model.conformal.alpha}"
                    ),
                    source=f"conformal ({drug_model.version})",
                    evidence_category="no_signal",
                ),
            ),
            target_present=gate.target_present,
            conformal_set=conformal_set,
        )

    if verdict == "likely_to_fail":
        confidence = p_resistant
    elif verdict == "likely_to_work":
        confidence = 1.0 - p_resistant
    else:  # ambiguous {S,R}
        confidence = max(p_resistant, 1.0 - p_resistant)

    features, evidence = _model_evidence(
        row,
        drug_model,
        antibiotic=drug_model.antibiotic,
        verdict=verdict,
        p_resistant=p_resistant,
    )
    return AntibioticPrediction(
        antibiotic=drug_model.antibiotic,
        verdict=verdict,
        calibrated_confidence=confidence,
        evidence_category="statistical_association",
        supporting_features=features,
        evidence=evidence,
        target_present=gate.target_present,
        conformal_set=conformal_set,
    )


def predict_antibiotic(
    vector: GenomeFeatureVector, antibiotic: str, registry: PredictorRegistry
) -> AntibioticPrediction:
    """The verdict for one (genome, antibiotic): gate -> model -> conformal, in that order.

    Fails loud on an annotation/schema-version mismatch BEFORE any verdict (the guard lives here,
    on the public single-drug entry, not only in predict_genome -- so no caller can bypass it).
    """
    _check_compatibility(vector, registry)
    gate = evaluate_gate(antibiotic, vector)
    if gate.result.fired:
        return _gate_prediction(antibiotic, gate)

    drug_model = registry.get(antibiotic)
    if drug_model is None:
        reason = registry.reason(antibiotic) or (
            f"no trained model for {antibiotic!r} (insufficient data or not in this registry)"
        )
        return _no_model_prediction(antibiotic, gate, reason=reason)
    return _model_prediction(vector, drug_model, gate)


def predict_genome(
    vector: GenomeFeatureVector, registry: PredictorRegistry
) -> tuple[AntibioticPrediction, ...]:
    """Every panel drug's verdict for one genome -- the per-genome firewall table.

    Raises AmrfinderDbVersionMismatchError / FeatureSchemaMismatchError up front if the
    genome's annotation basis disagrees with the trained models (fail loud): predict_antibiotic
    runs the compat check per drug, so the first (meropenem) call raises before any row is
    built -- an incompatible genome yields no partial table. Always returns one row per
    constants.SUPPORTED_ANTIBIOTICS, in that order.
    """
    return tuple(
        predict_antibiotic(vector, antibiotic, registry) for antibiotic in SUPPORTED_ANTIBIOTICS
    )
