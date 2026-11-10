"""Stage 7 – anomaly screening.

Three independent layers produce *flags for investigation*, never verdicts:

1. **Rule-based screening** with configurable thresholds.
2. **Robust statistical outliers** – median/MAD z-score of log10(AF) within
   each classification group.
3. **Isolation Forest** (optional) on a small numeric feature set.

Each flag is labelled with a ``kind``:

* ``data_quality`` – the record itself may be incomplete or inconsistent.
* ``biological_interest`` – the data look internally consistent but the
  frequency/classification combination is unusual and may reflect biology
  (founder effects, reduced penetrance, recessive carrier frequency,
  heterozygote advantage) or an interpretation that merits review.
* ``statistical_outlier`` – unusual relative to peers; no interpretation implied.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}


@dataclass
class AnomalyThresholds:
    pathogenic_af: float = 0.005        # P/LP with overall AF at or above this
    pathogenic_popmax_af: float = 0.01  # …or any eligible population AF at or above this
    ba1_af: float = 0.05                # ACMG/AMP BA1 stand-alone benign frequency
    rare_benign_af: float = 1e-5        # B/LB variants rarer than this
    low_an_fraction: float = 0.5        # AN below this fraction of the gene's median AN
    mad_z: float = 3.5                  # robust z-score cut-off
    use_isolation_forest: bool = True
    isolation_contamination: float = 0.02
    seed: int = 42

    @classmethod
    def from_dict(cls, d: dict | None) -> "AnomalyThresholds":
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _flag(row, category, kind, priority, evidence, explanation, score=0.0) -> dict:
    return {"variant_key": row.get("vcf_key"), "variant_id": row.get("id"),
            "provenance": row.get("provenance", "REAL"), "category": category, "kind": kind,
            "priority": priority, "score": round(float(score), 4), "evidence": evidence,
            "explanation": explanation}


def _fmt(af):
    return "n/a" if af is None else (f"{af:.2e}" if af < 1e-3 else f"{af:.4f}")


def rule_based(rows: list[dict], t: AnomalyThresholds) -> list[dict]:
    flags = []
    ans = [r["an"] for r in rows if r.get("in_gnomad") and r.get("an")]
    median_an = float(np.median(ans)) if ans else None
    for r in rows:
        if r.get("match_status") == "secondary_clinvar":
            continue
        af, popmax, cls = r.get("af"), r.get("popmax_af"), r.get("coarse_class")
        matched = r.get("in_gnomad") and r.get("in_clinvar")
        qc = set(r.get("qc_flags") or [])

        # ---- biologically interesting combinations ------------------------
        if matched and cls == "P_LP" and af is not None and (
                af >= t.pathogenic_af or (popmax or 0) >= t.pathogenic_popmax_af):
            high = af >= t.ba1_af or (popmax or 0) >= t.ba1_af
            flags.append(_flag(r, "frequent_pathogenic", "biological_interest", "high" if high else "medium",
                {"af": af, "popmax_af": popmax, "popmax_population": r.get("popmax_population"),
                 "thresholds": {"af": t.pathogenic_af, "popmax_af": t.pathogenic_popmax_af},
                 "classification": r.get("clinical_significance"), "review_status": r.get("review_status")},
                f"Classified {r.get('clinical_significance')} but observed at AF {_fmt(af)} overall"
                f" (highest eligible population: {r.get('popmax_population') or 'n/a'} at {_fmt(popmax)}). "
                "Possible explanations include recessive inheritance (healthy heterozygous carriers), reduced "
                "penetrance, founder effects or balancing selection – or a classification that merits review. "
                "This flag does not mean the variant is misclassified.",
                score=math.log10(max(af, popmax or 0) / t.pathogenic_af) + 1))
        if matched and cls in ("VUS", "CONFLICTING") and af is not None and \
                (af >= t.ba1_af or (popmax or 0) >= t.ba1_af):
            flags.append(_flag(r, "ba1_frequency_non_benign", "biological_interest", "high",
                {"af": af, "popmax_af": popmax, "ba1_threshold": t.ba1_af, "classification": r.get("clinical_significance")},
                f"{r.get('clinical_significance')} variant exceeds the ACMG/AMP BA1 frequency ({t.ba1_af:.0%}) "
                "in at least one population. Variants this common are usually considered benign for rare "
                "Mendelian disease, but gene-specific exceptions exist.", score=2.0))
        if matched and cls == "B_LB" and af is not None and af < t.rare_benign_af:
            flags.append(_flag(r, "rare_benign", "biological_interest", "low",
                {"af": af, "threshold": t.rare_benign_af, "review_status": r.get("review_status")},
                f"Classified {r.get('clinical_significance')} while very rare (AF {_fmt(af)}). Benign "
                "classifications are often based on functional or segregation evidence rather than frequency, "
                "so this is common and usually expected; listed for completeness.", score=0.3))
        if r.get("coarse_class") == "CONFLICTING":
            pr = "high" if (af or 0) >= t.pathogenic_af else "medium"
            flags.append(_flag(r, "conflicting_interpretation", "biological_interest", pr,
                {"clinical_significance": r.get("clinical_significance"), "review_status": r.get("review_status"),
                 "af": af, "in_gnomad": r.get("in_gnomad")},
                "ClinVar submitters disagree about this variant's clinical significance. The frequency data "
                f"(AF {_fmt(af)}) can be one line of evidence when reviewing the submissions.", score=1.0))

        # ---- data quality --------------------------------------------------
        if r.get("in_gnomad") and ({"missing_ac_an", "zero_an"} & qc):
            flags.append(_flag(r, "incomplete_frequency_record", "data_quality", "medium",
                {"ac": r.get("ac"), "an": r.get("an"), "qc_flags": sorted(qc)},
                "gnomAD record lacks a usable allele number, so AF cannot be computed.", score=1.0))
        bad = {"ac_exceeds_an", "negative_count", "af_out_of_range"} | {f for f in qc if f.endswith("af_inconsistent")}
        if bad & qc:
            flags.append(_flag(r, "count_inconsistency", "data_quality", "high",
                {"ac": r.get("ac"), "an": r.get("an"), "af": af, "qc_flags": sorted(bad & qc)},
                "Allele counts are internally inconsistent (AF ≠ AC/AN or AC > AN). Check the source record.",
                score=2.0))
        if r.get("in_gnomad") and "failed_gnomad_filter" in qc:
            flags.append(_flag(r, "gnomad_qc_filter", "data_quality", "medium" if matched else "low",
                {"filters": r.get("gnomad_filters")},
                "gnomAD marks this site as failing a quality filter in at least one call set; its frequency "
                "may be unreliable.", score=0.8))
        if median_an and r.get("in_gnomad") and r.get("an") and r["an"] < t.low_an_fraction * median_an:
            flags.append(_flag(r, "low_allele_number", "data_quality", "low",
                {"an": r["an"], "gene_median_an": median_an, "fraction": r["an"] / median_an},
                f"Allele number ({r['an']:,}) is below {t.low_an_fraction:.0%} of the gene median "
                f"({median_an:,.0f}), suggesting reduced coverage; AF estimates are less precise.",
                score=0.5))
        if r.get("in_clinvar") and ({"missing_alleles", "invalid_coordinates"} & qc):
            flags.append(_flag(r, "incomplete_clinvar_record", "data_quality", "low",
                {"clinvar_variation_id": r.get("clinvar_variation_id"), "qc_flags": sorted(qc)},
                "ClinVar record has no allele-level coordinates, so it cannot be matched to gnomAD.", score=0.3))
        if "ambiguous_match" in qc:
            flags.append(_flag(r, "ambiguous_match", "data_quality", "medium",
                {"match_method": r.get("match_method"), "other_clinvar_ids": r.get("other_clinvar_ids")},
                "More than one ClinVar record maps to this allele with different classifications, or the "
                "allele maps to several gnomAD records. Excluded from statistical tests by default.", score=1.0))
    return flags


def robust_outliers(rows: list[dict], t: AnomalyThresholds) -> list[dict]:
    flags = []
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("in_gnomad") and r.get("in_clinvar") and (r.get("af") or 0) > 0 and \
                r.get("coarse_class") in ("P_LP", "VUS", "B_LB") and r.get("match_status") != "secondary_clinvar":
            by_class.setdefault(r["coarse_class"], []).append(r)
    for cls, members in by_class.items():
        if len(members) < 10:
            continue
        x = np.log10([m["af"] for m in members])
        med = np.median(x)
        mad = np.median(np.abs(x - med))
        if mad == 0:
            continue
        z = 0.6745 * (x - med) / mad
        for m, zi in zip(members, z):
            if abs(zi) >= t.mad_z:
                direction = "higher" if zi > 0 else "lower"
                flags.append(_flag(m, "frequency_outlier_within_class", "statistical_outlier",
                    "medium" if abs(zi) >= t.mad_z + 1.5 else "low",
                    {"robust_z": float(zi), "class": cls, "class_median_log10_af": float(med),
                     "mad": float(mad), "threshold": t.mad_z, "af": m["af"]},
                    f"AF is unusually {direction} than other {cls.replace('_', '/')} variants in this gene "
                    f"(robust z = {zi:.1f}). This is a statistical observation only.", score=abs(float(zi)) / 3))
    return flags


def isolation_forest(rows: list[dict], t: AnomalyThresholds) -> list[dict]:
    from sklearn.ensemble import IsolationForest

    cand = [r for r in rows if r.get("in_gnomad") and (r.get("af") or 0) > 0 and r.get("an")]
    if len(cand) < 50:
        return []
    cls_ord = {"B_LB": 0, "VUS": 1, "CONFLICTING": 1.5, "P_LP": 2, "OTHER": 1, "NOT_IN_CLINVAR": 1}
    X = np.array([[math.log10(r["af"]), math.log10(r["an"]),
                   math.log10(max(r.get("popmax_af") or r["af"], 1e-9) / r["af"]),
                   cls_ord.get(r.get("coarse_class"), 1), r.get("gold_stars") or 0] for r in cand])
    model = IsolationForest(n_estimators=200, contamination=t.isolation_contamination, random_state=t.seed)
    model.fit(X)
    scores = -model.score_samples(X)
    labels = model.predict(X)
    flags = []
    for r, s, lab, x in zip(cand, scores, labels, X):
        if lab == -1:
            flags.append(_flag(r, "multivariate_outlier", "statistical_outlier", "low",
                {"isolation_score": float(s), "features": {"log10_af": x[0], "log10_an": x[1],
                 "log10_popmax_ratio": x[2], "class_ordinal": x[3], "gold_stars": x[4]},
                 "contamination": t.isolation_contamination},
                "Isolation Forest isolated this variant quickly using AF, AN, population skew, classification "
                "and review stars – its combination of features is uncommon in this gene.", score=float(s)))
    return flags


def detect_anomalies(rows: list[dict], thresholds: dict | None = None) -> dict:
    t = AnomalyThresholds.from_dict(thresholds)
    flags = rule_based(rows, t) + robust_outliers(rows, t)
    if t.use_isolation_forest:
        flags += isolation_forest(rows, t)
    flags.sort(key=lambda f: (PRIORITY_RANK[f["priority"]], f["score"]), reverse=True)
    summary: dict = {"total": len(flags), "by_category": {}, "by_kind": {}, "by_priority": {},
                     "flagged_variants": len({f["variant_key"] for f in flags})}
    for f in flags:
        for k, field in (("by_category", "category"), ("by_kind", "kind"), ("by_priority", "priority")):
            summary[k][f[field]] = summary[k].get(f[field], 0) + 1
    return {"thresholds": asdict(t), "summary": summary, "flags": flags}
