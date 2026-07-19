"""Feature builder (issue #17): AmrFeature calls -> a versioned, two-table GenomeFeatureVector.

Gene presence/absence table: `Element subtype == AMR` rows. Point-mutation table:
`Element subtype in {POINT, POINT_DISRUPT}`. STRESS/VIRULENCE hits (collected by
annotation/ via `--plus`) are intentionally excluded from both tables -- out of scope
for the MVP's ML feature matrix per research-findings/amrfinderplus-features.md, though
still present in the raw AmrFeature list for future RAG/evidence use. This mirrors a
real finding from validating against live AMRFinderPlus output: STRESS-type hits
legitimately carry no Class/Subclass at all (confirmed in both the TSV output and
ReferenceGeneCatalog.txt itself) -- that is not a data-quality gap to patch, only
AMR-subtype genes ever need the ReferenceGeneCatalog.txt fallback below.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from genome_firewall.schemas import AmrFeature, AmrMethod, GenomeFeatureVector

#: Bump when the AmrFeature -> GenomeFeatureVector transform changes shape (new/removed
#: field, changed semantics) -- predictor/predict.py (EPIC 3) will reject a mismatch
#: rather than silently reindex.
SCHEMA_VERSION = "1.0.0"

_PARTIAL_CONTIG_END_METHODS = frozenset({"PARTIAL_CONTIG_ENDX", "PARTIAL_CONTIG_ENDP"})


class ReferenceGeneCatalog:
    """Gene symbol -> (Class, Subclass) lookup, loaded from the pinned NCBI catalog
    (data/reference/ReferenceGeneCatalog.txt, ADR-0013).

    Used only to fill Class/Subclass when an AMR-subtype hit's own TSV columns are
    blank (Plus-scope/newly-curated genes) -- the large majority of hits already carry
    Class/Subclass directly from AMRFinderPlus and never touch this lookup.

    The catalog's `allele` column matches AMRFinderPlus's `Element symbol` directly for
    named alleles and point mutations (e.g. "blaTEM-1", "gyrA_S83Y"); genes without
    allele-level naming (e.g. "fieF") instead match on `gene_family`. Confirmed by
    inspection against the live pinned catalog -- both keys are tried, allele first.
    A gene_symbol can appear under multiple taxa with the same Class/Subclass (curated
    per-organism); first-occurrence-wins is safe here since values are consistent
    across taxa for the same allele in every case inspected.
    """

    def __init__(self, catalog_path: Path) -> None:
        by_allele: dict[str, tuple[str, str]] = {}
        by_gene_family: dict[str, tuple[str, str]] = {}
        with catalog_path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                drug_class, drug_subclass = row["class"], row["subclass"]
                if not drug_class or not drug_subclass:
                    continue
                allele, gene_family = row["allele"], row["gene_family"]
                if allele and allele not in by_allele:
                    by_allele[allele] = (drug_class, drug_subclass)
                if gene_family and gene_family not in by_gene_family:
                    by_gene_family[gene_family] = (drug_class, drug_subclass)
        self._by_allele = by_allele
        self._by_gene_family = by_gene_family

    def lookup(self, gene_symbol: str) -> tuple[str, str] | None:
        return self._by_allele.get(gene_symbol) or self._by_gene_family.get(gene_symbol)


def build_feature_vector(
    genome_id: str,
    features: tuple[AmrFeature, ...],
    *,
    amrfinder_db_version: str,
    catalog: ReferenceGeneCatalog | None = None,
) -> GenomeFeatureVector:
    """Pivot one genome's AmrFeature calls into its GenomeFeatureVector.

    `Method` is kept as an auxiliary per-gene QC column rather than collapsed away, and
    PARTIAL_CONTIG_END* hits are flagged separately from a hard PARTIAL cutoff since
    they are frequently assembly-fragmentation artifacts, not real partial genes.
    """
    gene_presence: dict[str, bool] = {}
    gene_presence_method: dict[str, AmrMethod] = {}
    gene_hit_count: dict[str, int] = {}
    gene_drug_class: dict[str, str] = {}
    gene_drug_subclass: dict[str, str] = {}
    point_mutations: dict[str, bool] = {}
    point_mutation_disrupt: dict[str, bool] = {}
    partial_contig_end_genes: set[str] = set()
    unmapped_class_genes: set[str] = set()

    for feature in features:
        if feature.element_subtype == "AMR":
            gene_presence[feature.gene_symbol] = True
            gene_hit_count[feature.gene_symbol] = gene_hit_count.get(feature.gene_symbol, 0) + 1
            gene_presence_method.setdefault(feature.gene_symbol, feature.method)
            if feature.method in _PARTIAL_CONTIG_END_METHODS:
                partial_contig_end_genes.add(feature.gene_symbol)

            resolved_class, resolved_subclass = feature.drug_class, feature.drug_subclass
            if catalog is not None and (resolved_class is None or resolved_subclass is None):
                looked_up = catalog.lookup(feature.gene_symbol)
                if looked_up is not None:
                    catalog_class, catalog_subclass = looked_up
                    resolved_class = resolved_class or catalog_class
                    resolved_subclass = resolved_subclass or catalog_subclass
            if resolved_class is None:
                unmapped_class_genes.add(feature.gene_symbol)
            else:
                gene_drug_class.setdefault(feature.gene_symbol, resolved_class)
                if resolved_subclass is not None:
                    gene_drug_subclass.setdefault(feature.gene_symbol, resolved_subclass)
        elif feature.element_subtype in ("POINT", "POINT_DISRUPT"):
            point_mutations[feature.gene_symbol] = True
            if feature.element_subtype == "POINT_DISRUPT":
                point_mutation_disrupt[feature.gene_symbol] = True
        # STRESS/VIRULENCE subtypes are intentionally not pivoted into either table.

    return GenomeFeatureVector(
        genome_id=genome_id,
        schema_version=SCHEMA_VERSION,
        amrfinder_db_version=amrfinder_db_version,
        gene_presence=gene_presence,
        gene_presence_method=gene_presence_method,
        gene_hit_count=gene_hit_count,
        gene_drug_class=gene_drug_class,
        gene_drug_subclass=gene_drug_subclass,
        point_mutations=point_mutations,
        point_mutation_disrupt=point_mutation_disrupt,
        partial_contig_end_genes=tuple(sorted(partial_contig_end_genes)),
        unmapped_class_genes=tuple(sorted(unmapped_class_genes)),
    )


def write_feature_schema(output_path: Path, *, amrfinder_db_version: str) -> None:
    """Write the versioned, machine-readable GenomeFeatureVector contract.

    This is the *structural* schema (field names/types/JSON Schema, this builder's
    version, the pinned AMRFinderPlus DB version it was validated against) -- not a
    fixed, enumerated gene list. A canonical ordered gene list only exists once a
    training cohort does (EPIC 3's model artifacts each ship their own trained-on
    feature_schema.json per research-findings/architecture.md); this file is what
    predictor/predict.py (EPIC 3) can check before that exists.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "amrfinder_db_version": amrfinder_db_version,
        "genome_feature_vector_json_schema": GenomeFeatureVector.model_json_schema(),
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
