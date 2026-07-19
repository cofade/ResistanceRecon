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


def _fake_ftps_download(
    responses: dict[str, fetch_bvbrc_data.FetchResult],
    calls: list[str],
):
    """Build a fake `ftps_download` keyed by the requested filename (last path segment),
    recording call order in `calls` -- for pinning ftps_download_flatfile's fallback
    order and stop-on-non-550 behavior (issue #41) without touching the network."""

    def fake(
        host: str,
        remote_path: str,
        dest,
        *,
        user: str = "anonymous",
        password: str = "guest",
        timeout: float = 60.0,
    ) -> fetch_bvbrc_data.FetchResult:
        name = remote_path.rsplit("/", 1)[-1]
        calls.append(name)
        return responses[name]

    return fake


def test_ftps_download_flatfile_falls_back_to_singular_on_550(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BV-BRC's flat-file name drifted plural->singular before and singular->plural
    since (issue #41); a clean 550 on the current default must fall back to the next
    known name, not fail outright."""
    calls: list[str] = []
    responses = {
        "PATRIC_genomes_AMR.txt": fetch_bvbrc_data.FetchResult(
            ok=False, source="x", error="error_perm: 550 not found"
        ),
        "PATRIC_genome_AMR.txt": fetch_bvbrc_data.FetchResult(
            ok=True, source="x", path=tmp_path / "PATRIC_genome_AMR.txt"
        ),
    }
    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", _fake_ftps_download(responses, calls))

    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, timeout=1.0
    )

    assert result.ok
    assert calls == ["PATRIC_genomes_AMR.txt", "PATRIC_genome_AMR.txt"]  # plural first


def test_ftps_download_flatfile_succeeds_on_first_try_no_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current-production happy path: the plural name is served, succeeds on the
    first attempt, and the singular legacy name is never even tried."""
    calls: list[str] = []
    responses = {
        "PATRIC_genomes_AMR.txt": fetch_bvbrc_data.FetchResult(
            ok=True, source="x", path=tmp_path / "PATRIC_genomes_AMR.txt"
        ),
    }
    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", _fake_ftps_download(responses, calls))

    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, timeout=1.0
    )

    assert result.ok
    assert calls == ["PATRIC_genomes_AMR.txt"]  # no fallback attempted


def test_ftps_download_flatfile_explicit_filename_is_pinned_exclusively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit `filename` override must never silently fall back to a name the
    caller didn't ask for, even if it 550s -- distinguishes a real pin from "unset"."""
    calls: list[str] = []
    responses = {
        "some_custom_name.txt": fetch_bvbrc_data.FetchResult(
            ok=False, source="x", error="error_perm: 550 not found"
        ),
    }
    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", _fake_ftps_download(responses, calls))

    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, filename="some_custom_name.txt", timeout=1.0
    )

    assert not result.ok
    assert calls == ["some_custom_name.txt"]  # never expanded to KNOWN_FLATFILE_NAMES


def test_ftps_download_flatfile_stops_on_425(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 425 (router-ALG data-channel block, §11.4) is not a naming problem -- retrying
    a different filename over the same blocked data channel cannot help, so the helper
    must stop after the first candidate rather than burn through the whole list."""
    calls: list[str] = []
    responses = {
        "PATRIC_genomes_AMR.txt": fetch_bvbrc_data.FetchResult(
            ok=False, source="x", error="error_perm: 425 Unable to build data connection"
        ),
        "PATRIC_genome_AMR.txt": fetch_bvbrc_data.FetchResult(
            ok=True, source="x", path=tmp_path / "PATRIC_genome_AMR.txt"
        ),
    }
    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", _fake_ftps_download(responses, calls))

    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, timeout=1.0
    )

    assert not result.ok
    assert "425" in (result.error or "")
    assert calls == ["PATRIC_genomes_AMR.txt"]  # did not try the second name


def test_ftps_download_flatfile_returns_last_550_when_all_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If every known name 550s, the server has drifted to a third name -- surface the
    actionable hint from the last attempt rather than swallowing it."""
    calls: list[str] = []
    responses = {
        name: fetch_bvbrc_data.FetchResult(
            ok=False, source="x", error=f"error_perm: 550 {name} not found"
        )
        for name in fetch_bvbrc_data.KNOWN_FLATFILE_NAMES
    }
    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", _fake_ftps_download(responses, calls))

    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, timeout=1.0
    )

    assert not result.ok
    assert calls == list(fetch_bvbrc_data.KNOWN_FLATFILE_NAMES)
    assert fetch_bvbrc_data.KNOWN_FLATFILE_NAMES[-1] in (result.error or "")
    # The exhausted-fallback context must be explicit, not just the single (possibly
    # already-tried) name the generic 550 hint names.
    assert "already tried every known name" in (result.error or "")


def test_cmd_fetch_labels_skips_when_fallback_name_already_exists_locally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file that landed under the singular fallback name on a previous run must be
    recognized as already-present on a re-run -- the pre-check looks at every known
    candidate (_flatfile_candidates), not just the plural default (issue #41 senior
    review round 2)."""
    (tmp_path / "PATRIC_genome_AMR.txt").write_text("genome_id\tantibiotic\n", encoding="utf-8")

    def fake(
        host: str,
        remote_path: str,
        dest: Path,
        *,
        user: str = "anonymous",
        password: str = "guest",
        timeout: float = 60.0,
    ) -> fetch_bvbrc_data.FetchResult:
        raise AssertionError("ftps_download must not be called when a candidate already exists")

    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", fake)
    args = fetch_bvbrc_data.build_parser().parse_args(["fetch-labels", "--out-dir", str(tmp_path)])
    assert args.func(args) == 0

    printed = capsys.readouterr().out
    assert "already exists; skipping" in printed
    assert "PATRIC_genome_AMR.txt" in printed


def test_cmd_fetch_labels_falls_back_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real `fetch-labels` CLI, driven end-to-end offline: the plural default 550s,
    the singular legacy name succeeds, and the file lands under the resolved name."""
    calls: list[str] = []

    def fake(
        host: str,
        remote_path: str,
        dest: Path,
        *,
        user: str = "anonymous",
        password: str = "guest",
        timeout: float = 60.0,
    ) -> fetch_bvbrc_data.FetchResult:
        name = remote_path.rsplit("/", 1)[-1]
        calls.append(name)
        if name == "PATRIC_genomes_AMR.txt":
            return fetch_bvbrc_data.FetchResult(ok=False, source="x", error="error_perm: 550 nf")
        dest.write_text("genome_id\tantibiotic\n", encoding="utf-8")
        return fetch_bvbrc_data.FetchResult(ok=True, source="x", path=dest)

    monkeypatch.setattr(fetch_bvbrc_data, "ftps_download", fake)
    args = fetch_bvbrc_data.build_parser().parse_args(["fetch-labels", "--out-dir", str(tmp_path)])
    assert args.func(args) == 0
    assert calls == ["PATRIC_genomes_AMR.txt", "PATRIC_genome_AMR.txt"]
    assert (tmp_path / "PATRIC_genome_AMR.txt").exists()
    printed = capsys.readouterr().out
    assert "AMR flat file: OK" in printed


def test_parse_facet_map_matches_real_solr_shape() -> None:
    """Synthetic payload matching the exact shape confirmed against the live BV-BRC
    API (Documentation/11-risks-and-technical-debt/README.md §11.4): json(nl,map)
    returns facets as {value: count, ...}, not Solr's default flat list."""
    payload = {
        "facet_counts": {
            "facet_fields": {
                "evidence": {
                    "Computational Method": 1728894,
                    "Laboratory Method": 85291,
                    "Computational Prediction": 0,
                }
            }
        }
    }
    parsed = fetch_bvbrc_data._parse_facet_map(payload, "evidence")
    assert parsed == {
        "Computational Method": 1728894,
        "Laboratory Method": 85291,
        "Computational Prediction": 0,
    }


def test_parse_facet_map_missing_field_returns_empty() -> None:
    payload = {"facet_counts": {"facet_fields": {}}}
    assert fetch_bvbrc_data._parse_facet_map(payload, "evidence") == {}


def test_cmd_crosscheck_end_to_end_offline(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Drives the real solr_facet -> _parse_facet_map -> print wiring in
    cmd_crosscheck, with solr_facet patched so no network call happens -- the gap
    round 2's fix left uncovered (only _parse_facet_map was tested in isolation)."""

    def fake_solr_facet(
        collection: str,
        rql: str,
        *,
        base_url: str = fetch_bvbrc_data.SOLR_BASE,
        timeout: float = 60.0,
    ) -> dict[str, object]:
        if "resistant_phenotype" in rql:
            return {"response": {"numFound": 19}}
        return {
            "facet_counts": {
                "facet_fields": {"evidence": {"Laboratory Method": 19, "Computational Method": 5}}
            }
        }

    monkeypatch.setattr(fetch_bvbrc_data, "solr_facet", fake_solr_facet)
    args = fetch_bvbrc_data.build_parser().parse_args(["crosscheck", "--flatfile", str(FLATFILE)])
    assert args.func(args) == 0

    printed = capsys.readouterr().out
    assert "numFound (same filter):" in printed
    assert "Laboratory Method: 19" in printed


def test_cmd_crosscheck_handles_facet_shape_drift_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """If BV-BRC ever reverts facet_fields to Solr's default flat-list shape,
    cmd_crosscheck must fail with a clean message, not an uncaught traceback."""

    def fake_solr_facet(
        collection: str,
        rql: str,
        *,
        base_url: str = fetch_bvbrc_data.SOLR_BASE,
        timeout: float = 60.0,
    ) -> dict[str, object]:
        if "resistant_phenotype" in rql:
            return {"response": {"numFound": 19}}
        return {"facet_counts": {"facet_fields": {"evidence": ["Laboratory Method", 19]}}}

    monkeypatch.setattr(fetch_bvbrc_data, "solr_facet", fake_solr_facet)
    args = fetch_bvbrc_data.build_parser().parse_args(["crosscheck", "--flatfile", str(FLATFILE)])
    assert args.func(args) == 0  # degrades gracefully, does not crash

    printed = capsys.readouterr().out
    assert "cross-check failed" in printed


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
