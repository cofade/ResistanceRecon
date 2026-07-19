"""Integration-test shape #7 (issue #28): the demo flow renders the firewall verdict table,
the evidence drill-down, and the non-dismissible lab-confirmation disclaimer banner. Driven by
Streamlit's in-process AppTest (no browser, no server), the bundled demo genome, the offline
MockAnnotator, and no LLM key. No Docker, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from genome_firewall import ui
from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER

_APP = Path(ui.__file__).resolve().parent / "app.py"


def _disclaimer_shown(app: AppTest) -> bool:
    return any(LAB_CONFIRMATION_DISCLAIMER in element.value for element in app.error)


@pytest.mark.integration
def test_bundled_genome_renders_firewall_table_and_disclaimer() -> None:
    app = AppTest.from_file(str(_APP), default_timeout=180).run()
    assert not app.exception
    assert _disclaimer_shown(app)  # banner present before any interaction

    app.button[0].click().run()  # "Analyze" the default bundled genome
    assert not app.exception

    markdown = " ".join(m.value for m in app.markdown)
    assert any(label in markdown for label in ("ALLOW", "BLOCK", "REVIEW"))
    subheaders = " ".join(s.value for s in app.subheader)
    assert "Firewall verdicts" in subheaders
    assert "Evidence drill-down" in subheaders
    assert _disclaimer_shown(app)  # still present after the run (non-dismissible on every render)


@pytest.mark.integration
def test_upload_mode_without_docker_shows_guidance() -> None:
    app = AppTest.from_file(str(_APP), default_timeout=180).run()
    app.radio[0].set_value("Upload FASTA").run()
    assert not app.exception

    info = " ".join(i.value for i in app.info)
    assert "Docker" in info
    assert _disclaimer_shown(app)
