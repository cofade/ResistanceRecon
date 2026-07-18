"""CI gate: enforce the LLM boundary (golden rule #1).

The deterministic prediction path must never import the LLM package. Fails with a
non-zero exit code if any module under the trust-critical packages imports
``genome_firewall.llm`` (directly or via ``from ... import``).

See Documentation/09-architecture-decisions/ADR-0006-llm-boundary-rag-reviewer-report-only.md
"""

from __future__ import annotations

import pathlib
import re
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "genome_firewall"
#: Packages that produce or feed verdicts/confidence and must stay LLM-free.
TRUST_CRITICAL = ("reader", "features", "predictor")
_LLM_IMPORT = re.compile(r"^\s*(from\s+genome_firewall\.llm|import\s+genome_firewall\.llm)", re.M)


def main() -> int:
    violations: list[str] = []
    for pkg in TRUST_CRITICAL:
        pkg_dir = SRC / pkg
        if not pkg_dir.exists():
            continue
        for path in pkg_dir.rglob("*.py"):
            if _LLM_IMPORT.search(path.read_text(encoding="utf-8")):
                violations.append(str(path.relative_to(SRC.parent)))
    if violations:
        print("LLM boundary violated — the prediction path must not import genome_firewall.llm:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("LLM import-boundary OK: prediction path is LLM-free.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
