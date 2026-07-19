"""Tests for the deterministic, one-directional target gate (issue #19, ADR-0018)."""

from __future__ import annotations

from typing import Any

import pytest

from genome_firewall.constants import SUPPORTED_ANTIBIOTICS
from genome_firewall.predictor.target_gate import evaluate_gate
from genome_firewall.schemas import GenomeFeatureVector


def _vector(**kwargs: Any) -> GenomeFeatureVector:
    base: dict[str, Any] = {
        "genome_id": "g1",
        "schema_version": "1.0.0",
        "amrfinder_db_version": "2026-05-15.1",
    }
    base.update(kwargs)
    return GenomeFeatureVector(**base)


def test_carbapenemase_forces_meropenem_failure() -> None:
    v = _vector(gene_presence={"blaKPC-2": True}, gene_drug_subclass={"blaKPC-2": "CARBAPENEM"})
    ev = evaluate_gate("meropenem", v)
    assert ev.result.fired is True
    assert ev.result.forced_verdict == "likely_to_fail"
    assert ev.matched_genes == ("blaKPC-2",)
    assert ev.target_present is True
    assert "CARBAPENEM" in ev.subclass_citations[0]


def test_carbapenemase_absent_does_not_fire_and_never_forces_work() -> None:
    # Porin disruption without a carbapenemase: the gate must NOT fire (left to the model),
    # and must NEVER force likely_to_work.
    v = _vector(point_mutation_disrupt={"ompK36_fs": True})
    ev = evaluate_gate("meropenem", v)
    assert ev.result.fired is False
    assert ev.result.forced_verdict is None


def test_narrow_shv_does_not_fire_ceftriaxone_but_esbl_does() -> None:
    narrow = _vector(
        gene_presence={"blaSHV-11": True}, gene_drug_subclass={"blaSHV-11": "BETA-LACTAM"}
    )
    assert evaluate_gate("ceftriaxone", narrow).result.fired is False

    esbl = _vector(
        gene_presence={"blaCTX-M-15": True}, gene_drug_subclass={"blaCTX-M-15": "CEPHALOSPORIN"}
    )
    assert evaluate_gate("ceftriaxone", esbl).result.fired is True


def test_carbapenemase_also_fires_ceftriaxone() -> None:
    v = _vector(gene_presence={"blaKPC-2": True}, gene_drug_subclass={"blaKPC-2": "CARBAPENEM"})
    assert evaluate_gate("ceftriaxone", v).result.fired is True


def test_ciprofloxacin_needs_a_combination() -> None:
    single = _vector(point_mutations={"gyrA_S83Y": True})
    assert evaluate_gate("ciprofloxacin", single).result.fired is False

    double = _vector(point_mutations={"gyrA_S83Y": True, "parC_S80I": True})
    assert evaluate_gate("ciprofloxacin", double).result.fired is True

    one_plus_pmqr = _vector(point_mutations={"gyrA_S83Y": True}, gene_presence={"qnrB1": True})
    assert evaluate_gate("ciprofloxacin", one_plus_pmqr).result.fired is True


def test_gentamicin_fires_on_rmtase_not_ame() -> None:
    ame_only = _vector(gene_presence={"aac(3)-IIa": True})
    assert evaluate_gate("gentamicin", ame_only).result.fired is False

    rmtase = _vector(gene_presence={"armA": True})
    assert evaluate_gate("gentamicin", rmtase).result.fired is True


def test_tmp_smx_fires_on_sul_or_dfr() -> None:
    assert evaluate_gate(
        "trimethoprim-sulfamethoxazole", _vector(gene_presence={"sul1": True})
    ).result.fired
    assert evaluate_gate(
        "trimethoprim-sulfamethoxazole", _vector(gene_presence={"dfrA14": True})
    ).result.fired


def test_out_of_panel_antibiotic_does_not_fire_and_target_is_unknown() -> None:
    ev = evaluate_gate("colistin", _vector(gene_presence={"mcr-1": True}))
    assert ev.result.fired is False
    assert ev.target_present is None


@pytest.mark.parametrize("antibiotic", SUPPORTED_ANTIBIOTICS)
def test_gate_is_one_directional_never_forces_work(antibiotic: str) -> None:
    # A pan-susceptible-looking genome (no resistance determinants) must never be gate-forced
    # to likely_to_work for any panel drug -- susceptibility is the model's call, not the gate's.
    clean = _vector(gene_presence={"someHousekeepingGene": True})
    ev = evaluate_gate(antibiotic, clean)
    assert ev.result.forced_verdict != "likely_to_work"
