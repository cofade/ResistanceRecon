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
