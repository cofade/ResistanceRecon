"""Typed predictor errors (issue #22).

The inference path (predict.py) must FAIL LOUD, never silently reindex or pad, when a
genome's feature vector was built under a different AMRFinderPlus DB version or feature
schema than the trained models expect -- a silent mismatch would attach a model's
coefficients to the wrong genes and quietly corrupt every verdict (golden rule #3:
Ground-Truth-First). Novel genes absent from the vocabulary are NOT an error (they are
dropped as out-of-vocabulary by features.build_feature_row and surfaced as an OOD signal);
only a *version* disagreement -- which means the whole annotation basis differs -- raises.

Pure and LLM-free (predictor/ is trust-critical).
"""

from __future__ import annotations


class PredictorError(RuntimeError):
    """Base class for every typed predictor-inference error."""


class CompatibilityError(PredictorError):
    """A genome's feature vector is incompatible with the trained models' contract."""

    def __init__(self, message: str, *, expected: str, actual: str) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class AmrfinderDbVersionMismatchError(CompatibilityError):
    """The genome was annotated with a different pinned AMRFinderPlus DB version (ADR-0013).

    Different DB versions can rename/retire gene symbols, so a model trained on one DB's
    vocabulary cannot be trusted on a genome called with another -- re-annotate with the
    pinned DB rather than predict on a mismatch.
    """

    def __init__(self, *, expected: str, actual: str) -> None:
        super().__init__(
            f"genome annotated with AMRFinderPlus DB version {actual!r} but the trained models "
            f"expect {expected!r}; re-annotate with the pinned DB (ADR-0013) before predicting",
            expected=expected,
            actual=actual,
        )


class FeatureSchemaMismatchError(CompatibilityError):
    """The genome's feature-builder schema_version differs from the models' training schema.

    A schema-version bump can change how raw calls become features (presence encoding, point
    mutation handling), so the column semantics no longer line up -- rebuild the vector with
    the matching feature_builder rather than predict on a mismatch.
    """

    def __init__(self, *, expected: str, actual: str) -> None:
        super().__init__(
            f"genome feature schema_version {actual!r} but the trained models were built under "
            f"{expected!r}; rebuild the feature vector with the matching feature_builder",
            expected=expected,
            actual=actual,
        )
