"""Tests for the shared AMR-mechanism predicates (antibiotic-panel.md gene groups)."""

from __future__ import annotations

from typing import Any

from genome_firewall.features import mechanisms
from genome_firewall.schemas import GenomeFeatureVector


def _vector(**kwargs: Any) -> GenomeFeatureVector:
    base: dict[str, Any] = {
        "genome_id": "g1",
        "schema_version": "1.0.0",
        "amrfinder_db_version": "2026-05-15.1",
    }
    base.update(kwargs)
    return GenomeFeatureVector(**base)


def test_carbapenemase_detected_by_subclass() -> None:
    v = _vector(
        gene_presence={"blaKPC-2": True},
        gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
    )
    assert mechanisms.carbapenemase_hits(v) == ("blaKPC-2",)
    assert mechanisms.cephalosporin_resistance_hits(v) == ("blaKPC-2",)
    assert mechanisms.esbl_ampc_hits(v) == ()


def test_narrow_shv_is_not_an_esbl() -> None:
    v = _vector(
        gene_presence={"blaSHV-11": True},
        gene_drug_subclass={"blaSHV-11": "BETA-LACTAM"},
    )
    assert mechanisms.esbl_ampc_hits(v) == ()
    assert mechanisms.cephalosporin_resistance_hits(v) == ()


def test_esbl_detected_by_subclass() -> None:
    v = _vector(
        gene_presence={"blaCTX-M-15": True},
        gene_drug_subclass={"blaCTX-M-15": "CEPHALOSPORIN"},
    )
    assert mechanisms.esbl_ampc_hits(v) == ("blaCTX-M-15",)


def test_rmtase_vs_ame_split() -> None:
    v = _vector(gene_presence={"armA": True, "rmtB": True, "aac(3)-IIa": True})
    assert mechanisms.rmtase_hits(v) == ("armA", "rmtB")
    assert mechanisms.ame_hits(v) == ("aac(3)-IIa",)


def test_pmqr_family() -> None:
    v = _vector(
        gene_presence={
            "qnrB1": True,
            "aac(6')-Ib-cr": True,
            "oqxA": True,
            "qepA1": True,
            "aac(3)-IIa": True,
        }
    )
    assert mechanisms.pmqr_hits(v) == ("aac(6')-Ib-cr", "oqxA", "qepA1", "qnrB1")


def test_sul_and_dfr() -> None:
    v = _vector(gene_presence={"sul1": True, "sul2": True, "dfrA14": True})
    assert mechanisms.sul_hits(v) == ("sul1", "sul2")
    assert mechanisms.dfr_hits(v) == ("dfrA14",)


def test_qrdr_mutations_counted() -> None:
    v = _vector(point_mutations={"gyrA_S83Y": True, "parC_S80I": True, "pbp3_ins": True})
    assert mechanisms.qrdr_mutations(v) == ("gyrA_S83Y", "parC_S80I")


def test_porin_disruption() -> None:
    v = _vector(point_mutation_disrupt={"ompK36_fs": True})
    assert mechanisms.porin_disruptions(v) == ("ompK36_fs",)
