"""Stage 6 – statistical analysis.

Every test returns a dict with: sample sizes, statistic, p-value, effect
size (+ CI where defined), assumption checks, and a plain-language
explanation. p-values from all tests in one run are corrected together
with Benjamini–Hochberg (FDR) and Bonferroni.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

from app.pipeline.matching import MATCHED_STATUSES

CLASS_ORDER = ["P_LP", "VUS", "B_LB", "CONFLICTING"]
MIN_GROUP_N = 5
RARE_AF = 1e-3  # 0.1 % – conventional "rare variant" boundary used for 2×2 tables


# ---------------------------------------------------------------------------
# Building blocks (each validated in tests/test_statistics.py)
# ---------------------------------------------------------------------------
def describe(values) -> dict:
    x = np.asarray([v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))], float)
    if x.size == 0:
        return {"n": 0}
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return {
        "n": int(x.size), "mean": float(x.mean()), "median": float(med),
        "std": float(x.std(ddof=1)) if x.size > 1 else None,
        "min": float(x.min()), "max": float(x.max()), "q1": float(q1), "q3": float(q3),
        "iqr": float(q3 - q1),
    }


def wilson_ci(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH-adjusted p-values (step-up, monotone, capped at 1)."""
    p = np.asarray(pvalues, float)
    m = p.size
    if m == 0:
        return []
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(adj, 1.0)
    return out.tolist()


def bonferroni(pvalues: list[float]) -> list[float]:
    m = len(pvalues)
    return [min(1.0, p * m) for p in pvalues]


def bootstrap_median_diff_ci(a, b, n_boot: int = 2000, seed: int = 0, alpha: float = 0.05):
    rng = np.random.default_rng(seed)
    a, b = np.asarray(a, float), np.asarray(b, float)
    ia = rng.integers(0, a.size, (n_boot, a.size))
    ib = rng.integers(0, b.size, (n_boot, b.size))
    diffs = np.median(a[ia], axis=1) - np.median(b[ib], axis=1)
    return float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))


def normality_check(x) -> dict:
    x = np.asarray(x, float)
    if x.size < 3:
        return {"test": "Shapiro–Wilk", "applicable": False, "reason": "n < 3"}
    sample = x if x.size <= 5000 else np.random.default_rng(0).choice(x, 5000, replace=False)
    if np.ptp(sample) == 0:
        return {"test": "Shapiro–Wilk", "applicable": False, "reason": "all values identical"}
    w, p = stats.shapiro(sample)
    return {"test": "Shapiro–Wilk", "applicable": True, "W": float(w), "p_value": float(p),
            "normal_at_0.05": bool(p >= 0.05), "n_tested": int(sample.size)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def mann_whitney(a, b, label_a: str, label_b: str, seed: int = 0) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    res = {"test": "Mann–Whitney U", "comparison": f"{label_a} vs {label_b}",
           "variable": "log10(allele frequency)", "n": {label_a: int(a.size), label_b: int(b.size)}}
    if a.size < MIN_GROUP_N or b.size < MIN_GROUP_N:
        res.update(ran=False, reason=f"Each group needs at least {MIN_GROUP_N} variants with a gnomAD AF.")
        return res
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided", method="auto")
    r_rb = 1 - 2 * u / (a.size * b.size)  # rank-biserial; positive => a tends to be smaller
    # Common-language effect size: P(a > b) + 0.5 P(a == b) = U / (n1 n2)
    cles = u / (a.size * b.size)
    levene = stats.levene(a, b, center="median")
    res.update(
        ran=True, statistic=float(u), p_value=float(p),
        effect_size={"name": "rank-biserial correlation", "value": float(-r_rb),
                     "common_language": float(cles),
                     "magnitude": _magnitude(abs(r_rb), (0.1, 0.3, 0.5))},
        median_difference_log10=float(np.median(a) - np.median(b)),
        median_difference_ci95=bootstrap_median_diff_ci(a, b, seed=seed),
        assumptions={
            "independent_observations": "Assumed: one row per distinct allele.",
            "normality": {label_a: normality_check(a), label_b: normality_check(b)},
            "equal_spread_levene_p": float(levene.pvalue),
            "why_nonparametric": "Allele frequencies are extremely right-skewed, so a rank-based test is used "
                                 "instead of a t-test. It compares whether values in one group tend to be larger.",
        },
        explanation=(f"The Mann–Whitney U test ranks all {a.size + b.size} variants by allele frequency and asks "
                     f"whether {label_a} variants tend to rank higher or lower than {label_b} variants. A small "
                     "p-value means a difference this large would be unlikely if both groups had the same "
                     "distribution. The rank-biserial correlation ranges from -1 to 1 (0 = no difference; "
                     f"positive = {label_a} tends to be more frequent)."),
    )
    return res


def chi_square_classification_by_frequency(df: pd.DataFrame) -> dict:
    bins = [-np.inf, 1e-5, 1e-4, 1e-3, 1e-2, np.inf]
    labels = ["<0.001%", "0.001–0.01%", "0.01–0.1%", "0.1–1%", "≥1%"]
    sub = df[df["coarse_class"].isin(["P_LP", "VUS", "B_LB"]) & df["af"].notna()].copy()
    res = {"test": "Chi-square test of independence", "variables": "classification × frequency bin"}
    if sub.empty:
        res.update(ran=False, reason="No matched variants with allele frequencies.")
        return res
    sub["bin"] = pd.cut(sub["af"], bins=bins, labels=labels, right=False)
    table = pd.crosstab(sub["coarse_class"], sub["bin"]).reindex(columns=labels, fill_value=0)
    table = table.loc[:, table.sum(axis=0) > 0]
    table = table.loc[table.sum(axis=1) > 0]
    res["contingency_table"] = {"rows": table.index.tolist(), "columns": [str(c) for c in table.columns],
                                "counts": table.values.tolist()}
    if table.shape[0] < 2 or table.shape[1] < 2:
        res.update(ran=False, reason="Need at least 2 classes and 2 frequency bins with data.")
        return res
    chi2, p, dof, expected = stats.chi2_contingency(table.values)
    frac_ok = float((expected >= 5).mean())
    n = int(table.values.sum())
    cramers_v = math.sqrt(chi2 / (n * (min(table.shape) - 1)))
    res.update(
        ran=True, statistic=float(chi2), dof=int(dof), p_value=float(p), n=n,
        expected_counts=np.round(expected, 2).tolist(),
        effect_size={"name": "Cramér's V", "value": cramers_v, "magnitude": _magnitude(cramers_v, (0.1, 0.3, 0.5))},
        assumptions={"expected_counts_ge_5_fraction": frac_ok,
                     "assumption_met": frac_ok >= 0.8 and bool((expected >= 1).all()),
                     "rule": "≥80 % of expected counts ≥ 5 and none < 1 (Cochran's rule)."},
        explanation=("The chi-square test asks whether the mix of classifications differs between frequency bins. "
                     "It compares observed counts with the counts expected if classification and frequency were "
                     "unrelated. Cramér's V (0–1) describes how strong the association is."),
    )
    if not res["assumptions"]["assumption_met"]:
        res["warning"] = "Expected counts are small; interpret the chi-square p-value with caution (see Fisher test)."
    return res


def fisher_pathogenic_vs_benign_rare(df: pd.DataFrame, threshold: float = RARE_AF) -> dict:
    sub = df[df["coarse_class"].isin(["P_LP", "B_LB"]) & df["af"].notna()]
    a = int(((sub.coarse_class == "P_LP") & (sub.af < threshold)).sum())
    b = int(((sub.coarse_class == "P_LP") & (sub.af >= threshold)).sum())
    c = int(((sub.coarse_class == "B_LB") & (sub.af < threshold)).sum())
    d = int(((sub.coarse_class == "B_LB") & (sub.af >= threshold)).sum())
    res = {"test": "Fisher's exact test", "variables": f"P/LP vs B/LB × (AF < {threshold:g} vs ≥ {threshold:g})",
           "table": {"rows": ["P_LP", "B_LB"], "columns": [f"AF<{threshold:g}", f"AF≥{threshold:g}"],
                     "counts": [[a, b], [c, d]]}, "n": a + b + c + d}
    if (a + b) == 0 or (c + d) == 0:
        res.update(ran=False, reason="Both P/LP and B/LB groups need matched variants.")
        return res
    odds, p = stats.fisher_exact([[a, b], [c, d]], alternative="two-sided")
    ci = None
    try:
        ci_obj = stats.contingency.odds_ratio([[a, b], [c, d]], kind="conditional").confidence_interval(0.95)
        ci = [float(ci_obj.low), float(ci_obj.high)]
    except Exception:  # noqa: BLE001 - CI undefined for degenerate tables
        pass
    res.update(
        ran=True, statistic=None if math.isinf(odds) else float(odds), p_value=float(p),
        effect_size={"name": "odds ratio (sample)", "value": None if math.isinf(odds) else float(odds),
                     "ci95_conditional": ci},
        assumptions={"note": "Exact test – valid for any cell size; observations assumed independent."},
        explanation=(f"Fisher's exact test checks whether P/LP variants are more often rare (AF < {threshold:g}) "
                     "than B/LB variants. The odds ratio says how many times higher the odds of being rare are "
                     "for P/LP variants. An odds ratio of 1 means no difference."),
    )
    return res


def spearman_af_vs_stars(df: pd.DataFrame) -> dict:
    sub = df[df["af"].notna() & df["gold_stars"].notna() & (df["af"] > 0)]
    res = {"test": "Spearman rank correlation", "variables": "log10(AF) vs ClinVar review stars", "n": int(len(sub))}
    if len(sub) < 10 or sub["gold_stars"].nunique() < 2:
        res.update(ran=False, reason="Need ≥10 matched variants and at least two review-star levels.")
        return res
    rho, p = stats.spearmanr(np.log10(sub["af"]), sub["gold_stars"])
    # Fisher z CI for rho
    n = len(sub)
    z = np.arctanh(rho)
    se = 1 / math.sqrt(n - 3)
    ci = [float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))]
    res.update(ran=True, statistic=float(rho), p_value=float(p),
               effect_size={"name": "Spearman's rho", "value": float(rho), "ci95_fisher_z": ci,
                            "magnitude": _magnitude(abs(rho), (0.1, 0.3, 0.5))},
               assumptions={"note": "Monotonic relationship assumed; review stars are ordinal (ties are common)."},
               explanation=("Spearman's rho measures whether more frequent variants tend to have more (or fewer) "
                            "ClinVar review stars. It uses ranks, so it works with skewed data. ρ ranges from -1 to 1."))
    return res


def _magnitude(v: float, cuts) -> str:
    small, medium, large = cuts
    if v < small:
        return "negligible"
    if v < medium:
        return "small"
    if v < large:
        return "medium"
    return "large"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def analysis_frame(rows: list[dict]) -> pd.DataFrame:
    cols = ["vcf_key", "coarse_class", "classification", "af", "ac", "an", "gold_stars",
            "match_status", "in_gnomad", "in_clinvar", "variant_type", "provenance", "popmax_af"]
    df = pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols)
    df["af"] = pd.to_numeric(df["af"], errors="coerce")
    df["gold_stars"] = pd.to_numeric(df["gold_stars"], errors="coerce")
    return df


def run_statistics(rows: list[dict], include_ambiguous: bool = False, seed: int = 0) -> dict:
    df = analysis_frame(rows)
    # "synthetic"/"custom" rows arrive already paired (frequency + label); real rows never carry that status
    allowed = {"exact", "normalized", "synthetic", "custom"} | ({"ambiguous"} if include_ambiguous else set())
    matched = df[df["match_status"].isin(allowed) & df["in_gnomad"].astype(bool)]
    with_af = matched[matched["af"].notna() & (matched["af"] > 0)]

    descriptive = {}
    for cls in CLASS_ORDER + ["NOT_IN_CLINVAR"]:
        src = with_af if cls != "NOT_IN_CLINVAR" else df[(df.match_status == "gnomad_only") & (df.af > 0)]
        vals = src[src.coarse_class == cls]["af"]
        d = describe(vals.tolist())
        if d["n"]:
            d["log10"] = describe(np.log10(vals).tolist())
        descriptive[cls] = d
    fine_counts = df[df.in_clinvar.astype(bool) & (df.match_status != "secondary_clinvar")] \
        .groupby("classification").size().to_dict()

    groups = {c: np.log10(with_af[with_af.coarse_class == c]["af"].to_numpy()) for c in ("P_LP", "VUS", "B_LB")}
    labels = {"P_LP": "P/LP", "VUS": "VUS", "B_LB": "B/LB"}
    tests = [
        mann_whitney(groups["P_LP"], groups["B_LB"], labels["P_LP"], labels["B_LB"], seed),
        mann_whitney(groups["P_LP"], groups["VUS"], labels["P_LP"], labels["VUS"], seed),
        mann_whitney(groups["VUS"], groups["B_LB"], labels["VUS"], labels["B_LB"], seed),
        chi_square_classification_by_frequency(matched),
        fisher_pathogenic_vs_benign_rare(matched),
        spearman_af_vs_stars(matched),
    ]
    ran = [t for t in tests if t.get("ran")]
    bh = benjamini_hochberg([t["p_value"] for t in ran])
    bf = bonferroni([t["p_value"] for t in ran])
    for t, pb, pf in zip(ran, bh, bf):
        t["p_adjusted_bh"] = pb
        t["p_adjusted_bonferroni"] = pf
        t["significant_fdr_0.05"] = pb < 0.05

    n_clinvar = int((df.in_clinvar.astype(bool) & (df.match_status != "secondary_clinvar")).sum())
    n_plp = int(((df.coarse_class == "P_LP") & (df.match_status != "secondary_clinvar")).sum())
    proportions = {"pathogenic_fraction_of_clinvar": {
        "successes": n_plp, "n": n_clinvar,
        "estimate": n_plp / n_clinvar if n_clinvar else None, "ci95_wilson": wilson_ci(n_plp, n_clinvar)}}
    hist = _log_af_histogram(with_af)
    clin = df[df.in_clinvar.astype(bool) & (df.match_status != "secondary_clinvar") & df.coarse_class.isin(CLASS_ORDER)]
    review = {c: {str(int(k)): int(v) for k, v in clin[clin.coarse_class == c]["gold_stars"].value_counts().items()}
              for c in CLASS_ORDER}
    in_gnomad = {c: {"in_gnomad": int(((clin.coarse_class == c) & clin.in_gnomad.astype(bool)).sum()),
                     "total": int((clin.coarse_class == c).sum())} for c in CLASS_ORDER}
    return {
        "sample": {"total_rows": int(len(df)), "matched_used": int(len(matched)), "matched_with_af": int(len(with_af)),
                   "include_ambiguous": include_ambiguous},
        "descriptive": descriptive,
        "classification_counts": {k: int(v) for k, v in fine_counts.items()},
        "tests": tests,
        "multiple_testing": {"method": "Benjamini–Hochberg FDR (primary) and Bonferroni", "m": len(ran),
                             "explanation": "Running several tests raises the chance of a false positive. "
                                            "Adjusted p-values account for the number of tests performed."},
        "proportions": proportions,
        "af_histogram": hist,
        "review_stars_by_class": review,
        "gnomad_presence_by_class": in_gnomad,
        "box_data": {c: with_af[with_af.coarse_class == c]["af"].tolist() for c in CLASS_ORDER},
    }


def _log_af_histogram(df: pd.DataFrame) -> dict:
    edges = np.arange(-7, 0.25, 0.25)
    out = {"edges": edges.tolist(), "counts": {}}
    for cls in CLASS_ORDER:
        v = np.log10(df[df.coarse_class == cls]["af"].to_numpy())
        out["counts"][cls] = np.histogram(np.clip(v, -7, 0), bins=edges)[0].tolist()
    return out
