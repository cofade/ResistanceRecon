"""Offline unit tests for scripts/fetch_bvbrc_data.py's pure functions and CLI.

These run in every `pytest` invocation (no `@pytest.mark.live`, no network) -- unlike
tests/scripts/test_fetch_bvbrc_live.py, which only runs opt-in against the real BV-BRC
endpoints. Per Documentation/11-risks-and-technical-debt/README.md §11.4, a hard-won
lesson pinned only by a CI-skipped live test doesn't count as pinned; these tests are
the actual pin for the RQL-encoding and FTPS-error-hint lessons.
"""

from __future__ import annotations

import json
from ftplib import error_perm
from pathlib import Path

import fetch_bvbrc_data
import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "bvbrc"
FLATFILE = FIXTURES_DIR / "patric_genome_amr_sample.tsv"
METADATA = FIXTURES_DIR / "genome_metadata_sample.tsv"


def test_rql_value_encodes_spaces() -> None:
    assert fetch_bvbrc_data._rql_value("Laboratory Method") == "Laboratory+Method"
    assert fetch_bvbrc_data._rql_value("meropenem") == "meropenem"


def test_evidence_vocabulary_rql_requests_map_facets() -> None:
    rql = fetch_bvbrc_data.evidence_vocabulary_rql(573)
    assert "eq(taxon_id,573)" in rql
    assert "json(nl,map)" in rql


def test_lab_ast_facet_rql_encodes_evidence_value() -> None:
    rql = fetch_bvbrc_data.lab_ast_facet_rql(573)
    assert "Laboratory+Method" in rql  # the space MUST be encoded -- raw "Laboratory Method" 400s
    assert "Laboratory Method" not in rql
    assert "json(nl,map)" in rql


@pytest.mark.parametrize(
    ("exc", "expected_hint_substring"),
    [
        (TimeoutError("timed out"), "VPN"),
        (
            error_perm("550 RELEASE_NOTES/x.txt: No such file or directory"),
            "PATRIC_genomes_AMR.txt",
        ),
        (error_perm("425 Unable to build data connection: Operation not permitted"), "FTP ALG"),
        (error_perm("530 Login incorrect"), "bv-brc-data-access.md"),
    ],
)
def test_describe_ftps_error_hints(exc: BaseException, expected_hint_substring: str) -> None:
    message = fetch_bvbrc_data._describe_ftps_error(exc)
    assert expected_hint_substring in message


def test_cmd_report_end_to_end_offline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The full `report` subcommand (issue #12's human-checkpoint) against the
    committed fixtures -- no network, exercises real argparse wiring."""
    out_path = tmp_path / "label_report.json"
    args = fetch_bvbrc_data.build_parser().parse_args(
        [
            "report",
            "--flatfile",
            str(FLATFILE),
            "--metadata",
            str(METADATA),
            "--out",
            str(out_path),
        ]
    )
    exit_code = args.func(args)
    assert exit_code == 0

    printed = capsys.readouterr().out
    assert "AMR Panel" in printed  # the unexpected evidence value must surface
    assert "HUMAN CHECKPOINT" in printed

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["raw_rows"] == 22
    assert report["evidence_vocabulary"]["Laboratory Method"] == 20
    assert report["lab_rows_after_filter"] == 19
    assert report["mlst"]["genomes_total"] == 5
