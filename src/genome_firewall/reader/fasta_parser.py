"""FASTA parsing/validation -> GenomeInput (issue #15).

Pure -- no network/Docker I/O, just Biopython's SeqIO over whatever handle/path is given.
Rejects content that would silently corrupt downstream annotation/feature-building rather
than letting a malformed upload flow further into the pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import IO

from Bio import SeqIO

from genome_firewall.constants import SUPPORTED_SPECIES
from genome_firewall.schemas import ContigRecord, GenomeInput

#: Uppercase IUPAC nucleotide codes (canonical bases + ambiguity codes); anything else
#: (e.g. protein one-letter codes) means this isn't a nucleotide assembly FASTA.
_VALID_NUCLEOTIDE_CHARS = frozenset("ACGTUNRYSWKMBDHV")
_CANONICAL_BASES = frozenset("ACGT")

#: Broad sanity net for a bacterial genome upload, not a precise K. pneumoniae bound
#: (typical assembly is ~5.3 Mb) -- wide enough to allow fragmented draft assemblies
#: while rejecting obviously-wrong uploads (a single gene, a human chromosome fragment).
_MAX_CONTIGS = 2000
_MIN_TOTAL_LENGTH = 100_000
_MAX_TOTAL_LENGTH = 20_000_000


class FastaParseError(ValueError):
    """The given content is not a usable genome assembly FASTA."""


def parse_fasta(
    handle: IO[str] | Path,
    *,
    genome_id: str,
    species: str = SUPPORTED_SPECIES[0],
) -> GenomeInput:
    """Parse and validate a genome assembly FASTA into a GenomeInput.

    `handle` is a file path or an already-open text stream (e.g. an uploaded file's
    content wrapped in `io.StringIO`) -- Biopython's SeqIO accepts either.

    `species` is deliberately not validated against `SUPPORTED_SPECIES` here -- FASTA
    parsing stays a structural check only; "not covered" messaging for an unsupported
    species is a report/UI concern (a later epic), not a reason to reject a
    structurally valid genome at the parse boundary.
    """
    try:
        # Biopython ships no complete inline type annotations for SeqIO.parse.
        records = list(SeqIO.parse(handle, "fasta"))  # type: ignore[no-untyped-call]
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise FastaParseError(f"could not read FASTA content: {exc}") from exc

    if not records:
        raise FastaParseError("no FASTA records found (empty input or not FASTA-formatted)")
    if len(records) > _MAX_CONTIGS:
        raise FastaParseError(
            f"{len(records)} contigs exceeds the sane maximum of {_MAX_CONTIGS} for a "
            "single bacterial genome assembly"
        )

    seen_ids: set[str] = set()
    contigs: list[ContigRecord] = []
    for record in records:
        contig_id = record.id
        if not contig_id:
            raise FastaParseError("a contig is missing an id (header line)")
        if contig_id in seen_ids:
            raise FastaParseError(f"duplicate contig id: {contig_id!r}")
        seen_ids.add(contig_id)

        sequence = str(record.seq).upper()
        if not sequence:
            raise FastaParseError(f"contig {contig_id!r} has an empty sequence")

        invalid_chars = set(sequence) - _VALID_NUCLEOTIDE_CHARS
        if invalid_chars:
            raise FastaParseError(
                f"contig {contig_id!r} contains non-nucleotide characters "
                f"{sorted(invalid_chars)!r} -- is this a protein FASTA?"
            )
        if _CANONICAL_BASES.isdisjoint(sequence):
            raise FastaParseError(
                f"contig {contig_id!r} has no canonical A/C/G/T bases (all ambiguous/N)"
            )

        contigs.append(
            ContigRecord(contig_id=contig_id, length=len(sequence), description=record.description)
        )

    total_length = sum(c.length for c in contigs)
    if not _MIN_TOTAL_LENGTH <= total_length <= _MAX_TOTAL_LENGTH:
        raise FastaParseError(
            f"total assembly length {total_length:,} bp is outside the sane range "
            f"({_MIN_TOTAL_LENGTH:,}-{_MAX_TOTAL_LENGTH:,} bp) for a bacterial genome upload"
        )

    return GenomeInput(genome_id=genome_id, species=species, contigs=tuple(contigs))
