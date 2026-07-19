"""Project-wide constants that must be enforced structurally, not by convention."""

from typing import Final

#: The mandatory human-oversight disclaimer. Enforced at three independent points:
#: (1) a Pydantic validator on GenomeReport, (2) the LLM-as-reviewer substring check,
#: (3) a non-dismissible banner in the Streamlit UI. Do not alter without an ADR.
LAB_CONFIRMATION_DISCLAIMER: Final[str] = (
    "This is decision support only — confirm every result with standard laboratory "
    "antimicrobial susceptibility testing before any clinical action."
)

#: Species covered at MVP. Anything outside this list is reported as "not covered".
SUPPORTED_SPECIES: Final[tuple[str, ...]] = ("Klebsiella pneumoniae",)

#: Antibiotic panel (see Documentation/research-findings/antibiotic-panel.md).
SUPPORTED_ANTIBIOTICS: Final[tuple[str, ...]] = (
    "meropenem",
    "ceftriaxone",
    "ciprofloxacin",
    "gentamicin",
    "trimethoprim-sulfamethoxazole",
)

#: NCBI taxon_id for the MVP species (see Documentation/research-findings/bv-brc-data-access.md).
KLEBSIELLA_PNEUMONIAE_TAXON_ID: Final[int] = 573


# ---------------------------------------------------------------------------
# Predictor thresholds (EPIC 3). Fixed by ADR-0003/0004/0005 and the binary SIR
# collapse policy (ADR-0017). Detail: Documentation/research-findings/ml-methodology.md
# and antibiotic-panel.md. Enforced structurally, not by convention.
# ---------------------------------------------------------------------------

#: Minimum-n gate (ADR-0004): a drug needs at least this many resistant AND susceptible
#: isolates after the grouped split (with a calibration fold left over) or it is reported
#: "insufficient data" rather than given an unreliable model -- the defensive-by-design
#: choice over silently producing a model no one should trust.
MIN_RESISTANT_PER_DRUG: Final[int] = 20
MIN_SUSCEPTIBLE_PER_DRUG: Final[int] = 20

#: Conformal significance (ADR-0004). Default 90% coverage; the sensitivity table over
#: CONFORMAL_ALPHA_GRID (coverage vs no-call rate) is reported alongside so the choice is
#: defensible rather than arbitrary. Err conservative (lower alpha -> more no-calls) per
#: the "always confirm with lab testing" positioning.
DEFAULT_CONFORMAL_ALPHA: Final[float] = 0.10
CONFORMAL_ALPHA_GRID: Final[tuple[float, ...]] = (0.05, 0.10, 0.20)

#: Fixed confidence reported when the deterministic known-mechanism gate fires. The gate
#: is authoritative over the model where it fires (a called resistance mechanism is a fact,
#: not a statistical estimate); honesty is preserved by evidence_category=known_mechanism,
#: not by a probability. See predictor/target_gate.py and ADR-0018.
KNOWN_MECHANISM_CONFIDENCE: Final[float] = 0.99

#: Binary SIR collapse policy (ADR-0017): only unambiguous Resistant/Susceptible rows train
#: the models. Intermediate, Nonsusceptible, and Susceptible-dose dependent are dropped as
#: ambiguous label-noise rather than force-mapped -- the defensive, lower-noise choice.
BINARY_RESISTANT_CLASSES: Final[frozenset[str]] = frozenset({"Resistant"})
BINARY_SUSCEPTIBLE_CLASSES: Final[frozenset[str]] = frozenset({"Susceptible"})
DROPPED_SIR_CLASSES: Final[frozenset[str]] = frozenset(
    {"Intermediate", "Nonsusceptible", "Susceptible-dose dependent"}
)
