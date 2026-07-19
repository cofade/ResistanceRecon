# ADR-0016 — HTTPS BV-BRC Data API fetch (genome_sequence + genome_amr); FTPS demoted to fallback

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 3 planning session). Amends ADR-0012.

## Context

ADR-0012 built the BV-BRC fetch on anonymous FTPS. §11.4 records that FTPS's data channel fails behind a consumer router's FTP ALG (`425 Unable to build data connection`) — a network constraint that blocks the real run on the developer's own network. The BV-BRC Data API also serves the same data over HTTPS: the `genome_amr` collection returns lab-AST rows and `genome_sequence` returns contig FASTA (media type `application/dna+fasta`), fully avoiding FTPS.

## Decision

Make the **HTTPS Data API the PRIMARY** fetch path and demote FTPS to a documented, still-tested fallback. `scripts/fetch_bvbrc_data.py` gains `solr_select_records` (paged record pulls), `fetch-labels-https` (lab-AST rows + MLST metadata written as the same flat-file TSVs `build_dataset` already consumes), and `https_fasta_download` (genome_sequence → atomic write). `fetch-fasta --transport https|ftps` defaults to `https`. **Validated live** against the real API this session (`tests/scripts/test_fetch_https_live.py`, opt-in `GF_RUN_LIVE=1`): both the labels select and a real K. pneumoniae genome FASTA download succeed and pass the sanity check.

## Consequences

- (+) Removes the FTPS router-ALG dependency from the critical path; the real run works on an ordinary network.
- (+) No new dependency — stdlib `urllib` only, reusing the existing Solr POST machinery.
- (−) **NEW pitfall** (recorded in §11.4 + CLAUDE.md): the Data API defaults to 25 rows and caps a page at 25,000, so a naive `genome_sequence` query **silently truncates** a multi-contig assembly's FASTA. Mitigated by `fasta_sanity_problem` — every download is checked against the genome record's contig count/length and rejected on mismatch or on hitting the limit ceiling.
- (−) The `genome` collection's `mlst` field format is not yet confirmed to match `dataset.parse_mlst`'s `scheme.st` expectation; an unexpected format falls back safely to singleton groups (ADR-0015) and is a to-validate item for the real run.
- FTPS (`ftps_download`, ADR-0012) is retained and unit-tested as the fallback branch.
