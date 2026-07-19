"""Re-expose the predictor synthetic cohort to the eval tests (120 genomes / 24 STs, a known
resistance structure so split/train/gate are all exercisable offline). Deterministic."""

from __future__ import annotations

import pytest

from tests.predictor.conftest import SyntheticCohort, make_synthetic_cohort


@pytest.fixture
def synthetic_cohort() -> SyntheticCohort:
    return make_synthetic_cohort()
