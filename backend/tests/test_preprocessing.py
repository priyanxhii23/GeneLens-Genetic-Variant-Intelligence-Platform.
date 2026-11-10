"""Data cleaning, AF calculation, missing data and classification normalisation."""
import math

import pytest

from app.pipeline.preprocessing import (
    flatten_gnomad_variant, gold_stars, normalize_classification, preprocess_clinvar, preprocess_gnomad,
)
from app.pipeline.validation import check_counts, compute_af
from tests.fixtures.sample_data import clinvar_records, gnomad_gene


@pytest.mark.parametrize("ac,an,expected", [(10, 100_000, 1e-4), (0, 50, 0.0), (5, 5, 1.0)])
def test_af_equals_ac_over_an(ac, an, expected):
    assert math.isclose(compute_af(ac, an), expected)


@pytest.mark.parametrize("ac,an", [(1, 0), (None, 10), (10, None), (11, 10), (-1, 10)])
def test_af_undefined_for_invalid_counts(ac, an):
    assert compute_af(ac, an) is None


def test_check_counts_flags():
    assert "zero_an" in check_counts(0, 0)
    assert "ac_exceeds_an" in check_counts(11, 10)
    assert "missing_ac_an" in check_counts(None, 10)
    assert "af_inconsistent" in check_counts(10, 100, 0.5)
    assert check_counts(10, 100, 0.1) == []


def test_every_gnomad_af_matches_ac_over_an():
    for r in preprocess_gnomad(gnomad_gene()):
        if r["an"]:
            assert math.isclose(r["af"], r["ac"] / r["an"])
        else:
            assert r["af"] is None and "zero_an" in r["qc_flags"]


def test_population_flattening_excludes_sex_strata_and_computes_grpmax():
    v = gnomad_gene()["variants"][0]
    r = flatten_gnomad_variant(v, "TESTG")
    ids = [p["id"] for p in r["populations"]]
    assert ids == ["afr", "nfe"]  # afr_XX excluded
    afr = next(p for p in r["populations"] if p["id"] == "afr")
    assert math.isclose(afr["af"], 8 / 10_000)
    assert r["popmax_population"] == "afr" and math.isclose(r["popmax_af"], 8e-4)


def test_failed_filter_flagged():
    r = next(x for x in preprocess_gnomad(gnomad_gene()) if x["vcf_key"] == "1-700-G-T")
    assert "failed_gnomad_filter" in r["qc_flags"]


@pytest.mark.parametrize("raw,fine,coarse", [
    ("Pathogenic", "pathogenic", "P_LP"),
    ("Likely pathogenic", "likely_pathogenic", "P_LP"),
    ("Pathogenic/Likely pathogenic", "pathogenic_likely_pathogenic", "P_LP"),
    ("Pathogenic; other", "pathogenic", "P_LP"),
    ("Uncertain significance", "uncertain_significance", "VUS"),
    ("Likely benign", "likely_benign", "B_LB"),
    ("Benign/Likely benign", "benign_likely_benign", "B_LB"),
    ("Benign, risk factor", "benign", "B_LB"),
    ("Conflicting classifications of pathogenicity", "conflicting", "CONFLICTING"),
    ("Conflicting interpretations of pathogenicity", "conflicting", "CONFLICTING"),
    ("risk factor", "other", "OTHER"),
    ("not provided", "not_provided", "OTHER"),
    (None, "not_provided", "OTHER"),
    ("", "not_provided", "OTHER"),
])
def test_classification_normalisation(raw, fine, coarse):
    assert normalize_classification(raw) == (fine, coarse)


@pytest.mark.parametrize("status,stars", [
    ("practice guideline", 4), ("reviewed by expert panel", 3),
    ("criteria provided, multiple submitters, no conflicts", 2),
    ("criteria provided, single submitter", 1), ("criteria provided, conflicting classifications", 1),
    ("no assertion criteria provided", 0), (None, None)])
def test_gold_stars(status, stars):
    assert gold_stars(status) == stars


def test_haplotype_records_get_no_coordinates():
    recs = preprocess_clinvar(clinvar_records())
    hap = next(r for r in recs if r["clinvar_variation_id"] == "5")
    assert hap["coords_valid"] is False
    assert "multi_allele_record" in hap["qc_flags"]
