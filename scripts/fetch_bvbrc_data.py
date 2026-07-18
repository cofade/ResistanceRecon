"""BV-BRC network fetch (EPIC 1 / issue #11): FTPS flat-file + FASTA download, Solr
cross-check, and the Phase-A count report (issue #12 human checkpoint).

All network I/O lives here -- pure transforms live in genome_firewall.predictor.dataset.
This module is intentionally outside src/ so it sits outside the mypy --strict and
coverage gates (see the EPIC 1 plan's boundary map); its network calls are exercised
only by @pytest.mark.live tests (tests/scripts/test_fetch_bvbrc_live.py), skipped by
default.

Two-phase workflow with a human checkpoint between them:

  Phase A (this file): fetch-labels -> report -> crosscheck -- STOP for human review --
  Phase B: fetch-fasta (this file) -> scripts/build_dataset.py

See Documentation/research-findings/bv-brc-data-access.md for the FTPS/Solr mechanics
this implements, and ADR-0001 for the evidence == 'Laboratory Method' filter.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

# FTP_TLS is the encrypted variant; bandit's blacklist rule flags any ftplib import without
# distinguishing FTP from FTP_TLS. See prot_p() for the encrypted-data-channel half of the
# guarantee. The suppression marker below is bare and trailing, deliberately alone on its
# line's comment, since bandit parses text following that marker as suppression test IDs.
from ftplib import FTP_TLS, all_errors  # nosec B402
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd

from genome_firewall.constants import KLEBSIELLA_PNEUMONIAE_TAXON_ID
from genome_firewall.predictor import dataset
from genome_firewall.predictor.dataset import LAB_EVIDENCE

DEFAULT_HOST = "ftp.bv-brc.org"
DEFAULT_FLATFILE = "PATRIC_genome_AMR.txt"
DEFAULT_METADATA_FILE = "genome_metadata"
RELEASE_NOTES_DIR = "RELEASE_NOTES"
SOLR_BASE = "https://www.bv-brc.org/api"


class FetchResult(NamedTuple):
    """The project's {ok, source, error} envelope (see Documentation/08-crosscutting-
    concepts/README.md), extended with the local destination path on success."""

    ok: bool
    source: str
    error: str | None = None
    path: Path | None = None


def ftps_download(
    host: str,
    remote_path: str,
    dest: Path,
    *,
    user: str = "anonymous",
    password: str = "guest",
    timeout: float = 60.0,
) -> FetchResult:
    """Download one file over FTPS (explicit TLS, encrypted data channel via PROT P)
    to `dest`, via a `.part` temp file + atomic rename so an interrupted download
    never leaves a truthy destination file.
    """
    source = f"ftps://{host}/{remote_path}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        ftps = FTP_TLS(timeout=timeout)
        ftps.connect(host, 21)
        ftps.login(user, password)
        ftps.prot_p()  # encrypt the data channel -- required, plain data is refused
        with tmp.open("wb") as fh:
            ftps.retrbinary(f"RETR {remote_path}", fh.write)
        ftps.quit()
        tmp.replace(dest)
        return FetchResult(ok=True, source=source, path=dest)
    except all_errors as exc:
        tmp.unlink(missing_ok=True)
        return FetchResult(ok=False, source=source, error=_describe_ftps_error(exc))


def _describe_ftps_error(exc: BaseException) -> str:
    """Turn a raw ftplib exception into an actionable message. Pure -- pinned by
    offline unit tests (tests/scripts/test_fetch_bvbrc_data.py), not only by the
    @pytest.mark.live tests that exercise the real failure (see Documentation/11-
    risks-and-technical-debt/README.md §11.4: 'FTPS behind a router FTP ALG').
    """
    if isinstance(exc, TimeoutError):
        hint = "FTPS control channel may be blocked -- try a VPN or the Data API fallback"
    elif "550" in str(exc):
        hint = (
            "file not found -- retry with --filename PATRIC_genomes_AMR.txt "
            "(BV-BRC's flat-file name has varied across releases)"
        )
    elif "425" in str(exc) or "data connection" in str(exc).lower():
        hint = (
            "passive-mode DATA channel blocked even though the control channel connected -- "
            "common behind routers with an FTP ALG that mishandles FTPS's encrypted control "
            "channel (e.g. many consumer routers); try a different network, disable the "
            "router's FTP helper/ALG, or use a VPN"
        )
    else:
        hint = (
            "verify host/credentials against Documentation/research-findings/bv-brc-data-access.md"
        )
    return f"{type(exc).__name__}: {exc} ({hint})"


def solr_facet(
    collection: str, rql: str, *, base_url: str = SOLR_BASE, timeout: float = 60.0
) -> dict[str, Any]:
    """POST an RQL query to a BV-BRC Data API (Solr) collection; return the parsed
    JSON envelope (``{"response": {"numFound": ...}, "facet_counts": {...}}``).

    POST body (not a URL query string) avoids the encoding pitfalls of long facet
    expressions documented in bv-brc-data-access.md. stdlib urllib.request only --
    this is a cross-check call, not worth a new project dependency.
    """
    if not base_url.startswith("https://"):
        raise ValueError("base_url must be https")
    request = urllib.request.Request(
        f"{base_url}/{collection}/",
        data=rql.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/rqlquery+x-www-form-urlencoded",
            "Accept": "application/solr+json",
        },
    )
    # Rationale for the nosec below: base_url is asserted https:// above, closing the
    # file:/custom-scheme risk this rule warns about.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        payload: dict[str, Any] = json.load(response)
    return payload


def _rql_value(value: str) -> str:
    """Percent/plus-encode an RQL literal value. A raw space (e.g. in ``"Laboratory
    Method"``) is invalid RQL syntax and returns HTTP 400 -- BV-BRC's own curl
    example encodes it as ``Laboratory+Method`` (confirmed empirically against the
    live API; see Documentation/research-findings/bv-brc-data-access.md)."""
    return value.replace(" ", "+")


def evidence_vocabulary_rql(taxon_id: int) -> str:
    """RQL: every distinct `evidence` value present for `taxon_id`, pre-filter --
    mirrors dataset.enumerate_evidence_values but against the live API. Requests
    ``json(nl,map)`` so the facet comes back as ``{value: count, ...}`` rather than
    Solr's default flat ``[value, count, value, count, ...]`` list."""
    return f"eq(taxon_id,{taxon_id})&facet((field,evidence,limit,50))&limit(1)&json(nl,map)"


def lab_ast_facet_rql(taxon_id: int) -> str:
    """RQL: numFound + per-antibiotic/per-phenotype facets for lab-only AST rows --
    the live-side cross-check for dataset.per_drug_label_counts."""
    return (
        f"and(eq(taxon_id,{taxon_id}),eq(evidence,{_rql_value(LAB_EVIDENCE)}))"
        "&facet((field,antibiotic,limit,200),(field,resistant_phenotype,limit,20))"
        "&limit(1)&json(nl,map)"
    )


def _print_result(label: str, result: FetchResult) -> None:
    if result.ok:
        print(f"{label}: OK -> {result.path}")
    else:
        print(f"{label}: FAILED ({result.source}) -- {result.error}")


def cmd_fetch_labels(args: argparse.Namespace) -> int:
    """Phase A: FTPS-download the AMR flat file (+ optional genome_metadata). No
    FASTAs -- that's fetch-fasta, gated behind the human checkpoint in `report`."""
    out_dir = Path(args.out_dir)
    dest = out_dir / args.filename
    if dest.exists() and not args.overwrite:
        print(f"{dest} already exists; skipping (use --overwrite to re-download).")
    else:
        result = ftps_download(
            args.host, f"{RELEASE_NOTES_DIR}/{args.filename}", dest, timeout=args.timeout
        )
        _print_result("AMR flat file", result)
        if not result.ok:
            return 1
    if args.also_metadata:
        meta_dest = out_dir / DEFAULT_METADATA_FILE
        if meta_dest.exists() and not args.overwrite:
            print(f"{meta_dest} already exists; skipping (use --overwrite to re-download).")
        else:
            result = ftps_download(
                args.host,
                f"{RELEASE_NOTES_DIR}/{DEFAULT_METADATA_FILE}",
                meta_dest,
                timeout=args.timeout,
            )
            _print_result("genome_metadata", result)
            if not result.ok:
                return 1
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Phase A: pure evidence enumeration + per-drug count report -- the issue #12
    human checkpoint. No network; runs equally well on the committed test fixtures
    for a dry run (see the EPIC 1 plan's Verification section)."""
    raw_df = dataset.parse_amr_flatfile(Path(args.flatfile), taxon_id=args.taxon_id)
    evidence_counts = dataset.enumerate_evidence_values(raw_df)
    sir_counts_raw = dataset.enumerate_sir_values(raw_df)

    evidence_values = (
        tuple(v.strip() for v in args.evidence.split(","))
        if args.evidence
        else (dataset.LAB_EVIDENCE,)
    )
    require_typing_method = not args.no_require_typing_method
    lab_rows = dataset.filter_lab_ast(
        raw_df, evidence_values=evidence_values, require_typing_method=require_typing_method
    )
    working = dataset.attach_canonical_columns(lab_rows)
    per_drug = dataset.per_drug_label_counts(working)
    standard_breakdown = dataset.per_drug_standard_breakdown(working)

    print(f"Raw rows (taxon_id={args.taxon_id}): {len(raw_df)}")
    print("\nEvidence vocabulary (ALL rows, pre-filter):")
    for value, count in evidence_counts.items():
        print(f"  {value}: {count}")
    print(f"\nFilter applied: evidence in {evidence_values}")
    print(f"require_typing_method={require_typing_method}")
    print(f"Lab-AST rows after filter: {len(lab_rows)}")

    print("\nPer-drug label counts (rows; SIR classes; unique genomes):")
    print(per_drug.to_string(index=False) if not per_drug.empty else "  (none)")

    print("\nPer-drug testing-standard breakdown (CLSI / EUCAST / other-or-blank):")
    print(standard_breakdown.to_string(index=False) if not standard_breakdown.empty else "  (none)")

    mlst_summary: dict[str, object] | None = None
    if args.metadata:
        genome_metadata = dataset.parse_genome_metadata(Path(args.metadata), taxon_id=args.taxon_id)
        total = len(genome_metadata)
        with_st = (
            int(genome_metadata["mlst_st"].notna().sum())
            if "mlst_st" in genome_metadata.columns
            else 0
        )
        missing_fraction = (total - with_st) / total if total else 0.0
        mlst_summary = {
            "genomes_total": total,
            "with_st": with_st,
            "missing_fraction": missing_fraction,
        }
        print(
            f"\nMLST coverage: {with_st}/{total} genomes have a sequence type "
            f"(missing_fraction={missing_fraction:.2%})"
        )

    if args.out:
        report = {
            "raw_rows": len(raw_df),
            "evidence_vocabulary": {str(k): int(v) for k, v in evidence_counts.items()},
            "sir_vocabulary_raw": {str(k): int(v) for k, v in sir_counts_raw.items()},
            "evidence_values_kept": list(evidence_values),
            "require_typing_method": require_typing_method,
            "lab_rows_after_filter": len(lab_rows),
            "per_drug": per_drug.to_dict(orient="records"),
            "standard_breakdown": standard_breakdown.to_dict(orient="records"),
            "mlst": mlst_summary,
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote {out_path}")

    print(
        "\n--- HUMAN CHECKPOINT (issue #12) ---\n"
        "Review the counts above: confirm the evidence filter, check whether any locked\n"
        "panel drug (esp. ceftriaxone) is under a viable min-n (swap + ADR if so), and\n"
        "pick a --cap for `fetch-fasta` before downloading any FASTAs."
    )
    return 0


def _parse_facet_map(payload: dict[str, Any], field: str) -> dict[str, int]:
    """Extract a ``json(nl,map)``-shaped Solr facet as ``{value: count, ...}``.

    Pure -- pinned by an offline test against a synthetic payload matching the real
    shape (Documentation/11-risks-and-technical-debt/README.md §11.4: 'RQL values
    need form-encoding; json(nl,map) changes the facet response shape').
    """
    facet = payload.get("facet_counts", {}).get("facet_fields", {}).get(field, {})
    return {str(k): int(v) for k, v in facet.items()}


def cmd_crosscheck(args: argparse.Namespace) -> int:
    """Phase A: compare local flat-file counts against the BV-BRC Solr Data API. The
    local flat file remains source of truth; this only flags drift to investigate."""
    raw_df = dataset.parse_amr_flatfile(Path(args.flatfile), taxon_id=args.taxon_id)
    local_lab_rows = len(dataset.filter_lab_ast(raw_df))
    local_unique_genomes = raw_df["genome_id"].nunique()

    try:
        payload = solr_facet("genome_amr", lab_ast_facet_rql(args.taxon_id), timeout=args.timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Solr cross-check failed: {type(exc).__name__}: {exc}")
        print("This is a cross-check only -- the local flat-file count remains source of truth.")
        return 1

    remote_num_found = payload.get("response", {}).get("numFound")
    print(f"Local lab-AST rows (evidence=='Laboratory Method'): {local_lab_rows}")
    print(f"Local unique genome_ids in flat file:                {local_unique_genomes}")
    print(f"Solr numFound (same filter):                          {remote_num_found}")
    if remote_num_found is not None:
        delta = abs(local_lab_rows - int(remote_num_found))
        verdict = "matches" if delta == 0 else "investigate before trusting counts"
        print(f"Delta: {delta}  ({verdict})")

    try:
        evidence_payload = solr_facet(
            "genome_amr", evidence_vocabulary_rql(args.taxon_id), timeout=args.timeout
        )
        remote_evidence = _parse_facet_map(evidence_payload, "evidence")
    except (urllib.error.URLError, TimeoutError, OSError, AttributeError, TypeError) as exc:
        # AttributeError/TypeError cover a BV-BRC response-shape drift in _parse_facet_map
        # (e.g. facet_fields ever reverting to Solr's flat-list default) -- fail with a clean
        # message here rather than an uncaught traceback from a dev cross-check tool.
        print(f"\nSolr evidence-vocabulary cross-check failed: {type(exc).__name__}: {exc}")
        return 0
    print("\nSolr evidence vocabulary (ALL rows for this taxon, pre-filter):")
    for value, count in sorted(remote_evidence.items(), key=lambda kv: -kv[1]):
        print(f"  {value}: {count}")
    return 0


def _download_with_retries(
    host: str, remote_path: str, dest: Path, *, retries: int, backoff: float, timeout: float
) -> FetchResult:
    result = ftps_download(host, remote_path, dest, timeout=timeout)
    attempt = 1
    while not result.ok and attempt < retries:
        time.sleep(backoff * attempt)
        result = ftps_download(host, remote_path, dest, timeout=timeout)
        attempt += 1
    return result


def cmd_fetch_fasta(args: argparse.Namespace) -> int:
    """Phase B: FTPS-download .fna for the selected genome_ids. Run only after
    reviewing `report`'s human checkpoint. Idempotent (skips existing non-empty
    files) and resumable (retries with backoff; a `.cap` bounds the run).

    NOTE(EPIC 2): these .fna files are the input to AMRFinderPlus, which builds
    feature_matrix.parquet -- that step is NOT implemented here (see the EPIC 1
    plan's Deferral safety section and the carry-forward comment on issue #11).
    """
    labels = pd.read_parquet(args.from_labels)
    antibiotics = (
        tuple(a.strip() for a in args.antibiotics.split(",")) if args.antibiotics else None
    )
    genome_ids = dataset.select_genome_ids(
        labels, antibiotics=antibiotics, min_n_per_drug=args.min_n
    )
    if args.genome_ids_file:
        extra_ids = [
            line.strip()
            for line in Path(args.genome_ids_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        genome_ids = sorted(set(genome_ids) | set(extra_ids))
    if args.cap is not None:
        genome_ids = genome_ids[: args.cap]
        print(
            "NOTE: --cap truncates the globally sorted genome_id list, not stratified per "
            "antibiotic -- a low cap can zero out a rarer panel drug's genomes. Use --antibiotics "
            "to scope the cap to one drug at a time if that matters for this run."
        )

    print(f"Selected {len(genome_ids)} genome_id(s) for FASTA download (cap={args.cap}).")
    out_dir = Path(args.out_dir)
    failures: list[str] = []
    downloaded = 0
    skipped = 0
    for genome_id in genome_ids:
        dest = out_dir / genome_id / f"{genome_id}.fna"
        if dest.exists() and dest.stat().st_size > 0 and not args.overwrite:
            skipped += 1
            continue
        remote_path = f"genomes/{genome_id}/{genome_id}.fna"
        result = _download_with_retries(
            args.host,
            remote_path,
            dest,
            retries=args.retries,
            backoff=args.backoff,
            timeout=args.timeout,
        )
        if result.ok:
            downloaded += 1
        else:
            failures.append(f"{genome_id}: {result.error}")

    print(
        f"Downloaded: {downloaded}, skipped (already present): {skipped}, failed: {len(failures)}"
    )
    for failure in failures:
        print(f"  FAILED {failure}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "BV-BRC lab-AST data fetch (EPIC 1). Network I/O only -- pure transforms live in "
            "genome_firewall.predictor.dataset. Phase A: fetch-labels -> report -> crosscheck -- "
            "human checkpoint -- Phase B: fetch-fasta -> scripts/build_dataset.py."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch_labels = sub.add_parser(
        "fetch-labels",
        help="Phase A: FTPS-download the AMR flat file (+ optional genome_metadata).",
    )
    fetch_labels.add_argument("--host", default=DEFAULT_HOST)
    fetch_labels.add_argument("--filename", default=DEFAULT_FLATFILE)
    fetch_labels.add_argument("--out-dir", default="data/raw/bvbrc")
    fetch_labels.add_argument("--also-metadata", action="store_true")
    fetch_labels.add_argument("--timeout", type=float, default=60.0)
    fetch_labels.add_argument("--overwrite", action="store_true")
    fetch_labels.set_defaults(func=cmd_fetch_labels)

    report = sub.add_parser(
        "report",
        help="Phase A: evidence enumeration + per-drug counts (issue #12 checkpoint). No network.",
    )
    report.add_argument("--flatfile", required=True)
    report.add_argument("--metadata")
    report.add_argument("--taxon-id", type=int, default=KLEBSIELLA_PNEUMONIAE_TAXON_ID)
    report.add_argument(
        "--evidence", help="Comma-separated evidence values to keep (default: 'Laboratory Method')."
    )
    report.add_argument("--no-require-typing-method", action="store_true")
    report.add_argument(
        "--out", help="Write the report as JSON (e.g. data/processed/label_report.json)."
    )
    report.set_defaults(func=cmd_report)

    crosscheck = sub.add_parser(
        "crosscheck",
        help="Phase A: compare local flat-file counts against the BV-BRC Solr Data API.",
    )
    crosscheck.add_argument("--flatfile", required=True)
    crosscheck.add_argument("--taxon-id", type=int, default=KLEBSIELLA_PNEUMONIAE_TAXON_ID)
    crosscheck.add_argument("--timeout", type=float, default=60.0)
    crosscheck.set_defaults(func=cmd_crosscheck)

    fetch_fasta = sub.add_parser(
        "fetch-fasta",
        help="Phase B: FTPS-download .fna for selected genome_ids. Run only after `report` review.",
    )
    fetch_fasta.add_argument("--from-labels", required=True, help="Path to labels.parquet")
    fetch_fasta.add_argument("--antibiotics", help="Comma-separated finalized panel; default: all")
    fetch_fasta.add_argument("--min-n", type=int)
    fetch_fasta.add_argument(
        "--cap", type=int, help="Human-chosen download cap (see report's checkpoint)."
    )
    fetch_fasta.add_argument("--genome-ids-file")
    fetch_fasta.add_argument("--host", default=DEFAULT_HOST)
    fetch_fasta.add_argument("--out-dir", default="data/raw/bvbrc/genomes")
    fetch_fasta.add_argument("--retries", type=int, default=3)
    fetch_fasta.add_argument("--backoff", type=float, default=2.0)
    fetch_fasta.add_argument("--timeout", type=float, default=60.0)
    fetch_fasta.add_argument("--overwrite", action="store_true")
    fetch_fasta.set_defaults(func=cmd_fetch_fasta)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
