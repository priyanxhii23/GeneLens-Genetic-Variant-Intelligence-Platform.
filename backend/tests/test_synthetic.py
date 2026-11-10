"""Synthetic generation: reproducibility, consistency, provenance, no copying."""
import math

import pytest

from app.pipeline import synthetic as syn
from app.pipeline.matching import match_variants
from app.pipeline.preprocessing import preprocess_clinvar, preprocess_gnomad
from tests.fixtures.sample_data import clinvar_records, gnomad_gene


def _gen(**kw):
    p = syn.SyntheticParams(**{"n_records": 300, "seed": 11, **kw})
    return syn.generate(p, dict(syn.DEFAULT_MODEL), "testjob")


def test_reproducible_with_seed():
    assert _gen() == _gen()
    assert _gen() != _gen(seed=12)


def test_every_record_is_labelled_synthetic():
    for r in _gen():
        assert r["provenance"] == "SYNTHETIC"
        assert r["vcf_key"].startswith("SYN-") and r["chrom"] == "SYN"
        assert "(simulated)" in r["clinical_significance"]
        assert r["conditions"] is None and r["review_status"] is None  # no fabricated evidence


def test_counts_are_internally_consistent():
    for r in _gen():
        assert 0 < r["ac"] <= r["an"]
        assert math.isclose(r["af"], r["ac"] / r["an"])
        assert r["ac"] == sum(p["ac"] for p in r["populations"])
        assert r["an"] == sum(p["an"] for p in r["populations"])


def test_missing_conflicting_and_unusual_injection():
    recs = _gen(missing_rate=0.1, conflicting_rate=0.1, unusual_rate=0.1)
    assert sum("simulated_conflict" in r["qc_flags"] for r in recs) == 30
    assert sum("simulated_unusual_frequency" in r["qc_flags"] for r in recs) == 30
    assert sum(any(f.startswith("simulated_missing") for f in r["qc_flags"]) for r in recs) == 30
    frequent_p = [r for r in recs if "simulated_unusual_frequency" in r["qc_flags"] and r["coarse_class"] == "P_LP"
                  and r["af"] is not None]
    assert all(r["af"] > 1e-3 for r in frequent_p)


def test_class_distribution_respected():
    recs = syn.generate(syn.SyntheticParams(n_records=4000, seed=3, class_distribution={"P_LP": 1, "B_LB": 3}),
                        dict(syn.DEFAULT_MODEL), "j")
    frac = sum(r["coarse_class"] == "P_LP" for r in recs) / len(recs)
    assert abs(frac - 0.25) < 0.03
    assert {r["coarse_class"] for r in recs} == {"P_LP", "B_LB"}


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        syn.SyntheticParams(n_records=0).validate()
    with pytest.raises(ValueError):
        syn.SyntheticParams(missing_rate=0.9).validate()
    with pytest.raises(ValueError):
        syn.SyntheticParams(class_distribution={"BAD": 1}).validate()


def test_fit_from_real_does_not_copy_real_variants():
    rows, _ = match_variants(preprocess_gnomad(gnomad_gene()), preprocess_clinvar(clinvar_records()),
                             "GRCh38", "GRCh38")
    for r in rows:
        r["provenance"] = "REAL"
    model = syn.fit_model(rows, seed=0)
    assert model["source"] == "fitted_from_real"
    recs = syn.generate(syn.SyntheticParams(n_records=200, seed=1), model, "j")
    real_keys = {r["vcf_key"] for r in rows}
    assert not real_keys & {r["vcf_key"] for r in recs}
    # The fitted model holds only summary parameters - no per-variant data.
    import json
    blob = json.dumps(model)
    assert not any(k in blob for k in real_keys)
    assert len(blob) < 4000
    cmp = syn.compare(rows, recs)
    assert set(cmp["classes"]) == set(syn.CLASSES)


def test_parametric_default_when_no_real_data():
    assert syn.fit_model([], 0)["source"] == "parametric_default"
