"""Unit tests for deterministic evidence assembly + category tagging (ADR-0020)."""

from __future__ import annotations

from genome_firewall.report.evidence import assemble_evidence, known_mechanism_hits
from tests.report.conftest import vector


def test_gate_fired_cites_only_known_mechanism_evidence() -> None:
    bundle = assemble_evidence(
        "meropenem",
        vector(gene_presence={"blaKPC-2": True}, gene_drug_subclass={"blaKPC-2": "CARBAPENEM"}),
        gate_fired=True,
    )
    assert bundle.category == "known_mechanism"
    assert bundle.supporting_features == ("blaKPC-2",)
    assert all(item.evidence_category == "known_mechanism" for item in bundle.evidence)


def test_ame_is_known_mechanism_membership_for_gentamicin() -> None:
    # AME is a curated known mechanism (KB member) even though it does not fire the gate.
    hits = known_mechanism_hits(
        "gentamicin",
        vector(gene_presence={"aac(3)-IIa": True}, gene_drug_subclass={"aac(3)-IIa": "GENTAMICIN"}),
    )
    assert hits == ("aac(3)-IIa",)


def test_porin_disruption_is_known_mechanism_for_meropenem() -> None:
    bundle = assemble_evidence(
        "meropenem",
        vector(point_mutation_disrupt={"ompK36_disrupt": True}),
        gate_fired=False,
    )
    assert bundle.category == "known_mechanism"
    assert "ompK36_disrupt" in bundle.supporting_features


def test_model_features_are_statistical_association() -> None:
    bundle = assemble_evidence(
        "ceftriaxone",
        vector(),
        gate_fired=False,
        model_top_features=("eng:has_esbl_or_ampc",),
        model_version="lr-v1",
    )
    assert bundle.category == "statistical_association"
    assert bundle.supporting_features == ("eng:has_esbl_or_ampc",)
    assert bundle.evidence[0].evidence_category == "statistical_association"


def test_known_membership_wins_row_category_over_statistical() -> None:
    # A known KB hit + a model feature -> row is known_mechanism (strongest cited).
    bundle = assemble_evidence(
        "gentamicin",
        vector(gene_presence={"aac(3)-IIa": True}, gene_drug_subclass={"aac(3)-IIa": "GENTAMICIN"}),
        gate_fired=False,
        model_top_features=("eng:has_ame",),
        model_version="lr-v1",
    )
    assert bundle.category == "known_mechanism"
    assert set(bundle.supporting_features) == {"aac(3)-IIa", "eng:has_ame"}


def test_empty_vector_and_no_model_features_is_no_signal() -> None:
    bundle = assemble_evidence("ciprofloxacin", vector(), gate_fired=False)
    assert bundle.category == "no_signal"
    assert bundle.supporting_features == ()
    assert bundle.evidence == ()


def test_model_feature_matching_a_known_gene_is_not_double_cited() -> None:
    bundle = assemble_evidence(
        "gentamicin",
        vector(gene_presence={"aac(3)-IIa": True}, gene_drug_subclass={"aac(3)-IIa": "GENTAMICIN"}),
        gate_fired=False,
        model_top_features=("aac(3)-IIa",),  # same name as the known hit
        model_version="lr-v1",
    )
    assert bundle.supporting_features == ("aac(3)-IIa",)
    assert len(bundle.evidence) == 1
    assert bundle.evidence[0].evidence_category == "known_mechanism"
