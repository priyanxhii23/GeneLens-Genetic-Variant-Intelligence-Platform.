"""Statistical outputs validated against independently computed values."""
import math

import numpy as np
import pandas as pd
import pytest

from app.pipeline import statistics as st


def test_describe_matches_numpy():
    x = [1.0, 2.0, 3.0, 4.0, 10.0]
    d = st.describe(x)
    assert d["n"] == 5 and d["mean"] == 4.0 and d["median"] == 3.0
    assert math.isclose(d["std"], math.sqrt(sum((v - 4) ** 2 for v in x) / 4))
    assert (d["q1"], d["q3"], d["min"], d["max"]) == (2.0, 4.0, 1.0, 10.0)
    assert st.describe([None, float("nan")]) == {"n": 0}


def test_benjamini_hochberg_hand_example():
    # sorted p: .005 .01 .03 .04 ; p*m/rank: .02 .02 .04 .04
    assert np.allclose(st.benjamini_hochberg([0.01, 0.04, 0.03, 0.005]), [0.02, 0.04, 0.04, 0.02])
    assert st.bonferroni([0.01, 0.5]) == [0.02, 1.0]


def test_wilson_interval_known_value():
    lo, hi = st.wilson_ci(8, 10)
    assert math.isclose(lo, 0.4902, abs_tol=1e-4) and math.isclose(hi, 0.9433, abs_tol=1e-4)
    assert st.wilson_ci(0, 0) is None


def test_mann_whitney_u_and_effect_size_by_hand():
    a, b = np.array([1., 2, 3, 4, 5]), np.array([6., 7, 8, 9, 10])
    res = st.mann_whitney(a, b, "A", "B")
    # U_A counts pairs where a > b: zero -> complete separation
    assert res["statistic"] == 0
    assert math.isclose(res["effect_size"]["value"], -1.0)
    # exact two-sided p for n1=n2=5 complete separation = 2/252
    assert math.isclose(res["p_value"], 2 / 252, rel_tol=1e-6)
    assert res["median_difference_log10"] == -5.0


def test_mann_whitney_skips_small_groups():
    res = st.mann_whitney([1, 2], [3, 4, 5, 6, 7], "A", "B")
    assert res["ran"] is False and "at least" in res["reason"]


def _frame(pairs):
    return pd.DataFrame([{"coarse_class": c, "af": af, "gold_stars": 1} for c, af in pairs])


def test_fisher_odds_ratio_matches_hand_calculation():
    rows = [("P_LP", 1e-5)] * 8 + [("P_LP", 0.01)] * 2 + [("B_LB", 1e-5)] * 1 + [("B_LB", 0.01)] * 5
    res = st.fisher_pathogenic_vs_benign_rare(_frame(rows))
    assert res["table"]["counts"] == [[8, 2], [1, 5]]
    assert math.isclose(res["effect_size"]["value"], (8 * 5) / (2 * 1))
    # hypergeometric two-sided p computed independently
    from math import comb
    def pmf(k):  # P(a=k) with margins row1=10, col1=9, N=16
        return comb(10, k) * comb(6, 9 - k) / comb(16, 9)
    p_obs = pmf(8)
    p = sum(pmf(k) for k in range(3, 10) if pmf(k) <= p_obs * (1 + 1e-7))
    assert math.isclose(res["p_value"], p, rel_tol=1e-6)


def test_chi_square_matches_manual_formula():
    rows = ([("P_LP", 2e-6)] * 20 + [("P_LP", 5e-3)] * 5 + [("B_LB", 2e-6)] * 6 + [("B_LB", 5e-3)] * 19)
    res = st.chi_square_classification_by_frequency(_frame(rows))
    obs = np.array(res["contingency_table"]["counts"], float)
    exp = obs.sum(1, keepdims=True) * obs.sum(0, keepdims=True) / obs.sum()
    # scipy applies Yates' correction for 2x2 tables
    chi2 = (((np.abs(obs - exp) - 0.5) ** 2) / exp).sum()
    assert math.isclose(res["statistic"], chi2, rel_tol=1e-9)
    assert res["assumptions"]["assumption_met"] is True


def test_spearman_ci_contains_rho():
    rng = np.random.default_rng(0)
    af = 10 ** rng.uniform(-6, -2, 60)
    df = pd.DataFrame({"af": af, "gold_stars": (np.log10(af) > -4).astype(int) + rng.integers(0, 2, 60),
                       "coarse_class": "P_LP"})
    res = st.spearman_af_vs_stars(df)
    lo, hi = res["effect_size"]["ci95_fisher_z"]
    assert lo <= res["statistic"] <= hi and res["statistic"] > 0


def test_run_statistics_applies_multiple_testing(fake_clients):
    from app.pipeline.matching import match_variants
    from app.pipeline.preprocessing import preprocess_clinvar, preprocess_gnomad
    from tests.fixtures.sample_data import clinvar_records, gnomad_gene

    rows, _ = match_variants(preprocess_gnomad(gnomad_gene()), preprocess_clinvar(clinvar_records()),
                             "GRCh38", "GRCh38")
    out = st.run_statistics(rows)
    ran = [t for t in out["tests"] if t.get("ran")]
    assert ran, "at least one test should run on the fixture"
    for t in ran:
        assert t["p_adjusted_bh"] >= t["p_value"] - 1e-12
        assert t["p_adjusted_bonferroni"] >= t["p_adjusted_bh"] - 1e-12
    # ambiguous rows excluded by default
    assert out["sample"]["include_ambiguous"] is False
