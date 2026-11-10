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
    enrich(flags, rows)
    summary: dict = {"total": len(flags), "by_category": {}, "by_kind": {}, "by_priority": {},
                     "flagged_variants": len({f["variant_key"] for f in flags})}
    for f in flags:
        for k, field in (("by_category", "category"), ("by_kind", "kind"), ("by_priority", "priority")):
            summary[k][f[field]] = summary[k].get(f[field], 0) + 1
    return {"thresholds": asdict(t), "summary": summary, "flags": flags}


# ---------------------------------------------------------------------------
# Plain-language presentation of each flag (headline · reason · why · next step)
# ---------------------------------------------------------------------------
CATEGORY_TEXT: dict[str, tuple[str, str, str]] = {
    "frequent_pathogenic": (
        "Relatively frequent pathogenic classification",
        "An allele frequency that is high for a given disease can be evidence against pathogenicity, so this "
        "combination merits a closer look. However, frequency alone cannot establish misclassification: "
        "recessive inheritance (healthy heterozygous carriers), reduced penetrance, founder effects, disease "
        "prevalence and balancing selection can all explain a pathogenic allele being common in some populations.",
        "Review the ClinVar submission history, the condition's inheritance pattern and prevalence, a "
        "condition-specific maximum credible allele frequency, and frequency in the population with the highest AF."),
    "ba1_frequency_non_benign": (
        "Very common variant without a benign classification",
        "The ACMG/AMP guidelines treat an allele frequency above 5% (criterion BA1) as stand-alone evidence that a "
        "variant is benign for rare Mendelian disease. A non-benign classification at this frequency is unusual, "
        "although gene- and population-specific exceptions exist.",
        "Check whether the classification concerns a rare disease, whether the frequency is driven by one "
        "population, and whether a newer ClinVar submission reflects population data."),
    "rare_benign": (
        "Very rare variant classified as benign",
        "Benign classifications are often based on functional assays, segregation or computational evidence "
        "rather than frequency, so a rare benign variant is usually expected. It is listed so the frequency "
        "evidence can be seen alongside the classification.",
        "No action is usually needed. If relevant, review which evidence the submitters used for the benign call."),
    "conflicting_interpretation": (
        "Conflicting clinical interpretations",
        "Laboratories can disagree because they use different evidence, interpretation criteria, dates or "
        "condition definitions. The disagreement should be examined before drawing any conclusion about the variant.",
        "Review the ClinVar review status, each submitter's evidence and date, and condition-specific classifications."),
    "incomplete_frequency_record": (
        "Frequency record is incomplete",
        "Without a usable allele number (AN) the allele frequency cannot be calculated. Missing AN is not the same "
        "as a frequency of zero – the site may simply be poorly covered in the reference data.",
        "Check coverage for this position in the source browser before using its frequency."),
    "count_inconsistency": (
        "Allele counts are internally inconsistent",
        "The reported numbers do not agree with each other (for example AF ≠ AC/AN, or AC > AN). This points to a "
        "data or processing problem rather than biology.",
        "Compare the record with the source database and re-run the analysis; report persistent errors upstream."),
    "gnomad_qc_filter": (
        "Variant fails a quality filter",
        "The frequency dataset marks this site as failing a quality-control filter in at least one call set, so its "
        "frequency estimate may be unreliable.",
        "Treat the frequency cautiously; check the filter reason and read depth in the source browser."),
    "low_allele_number": (
        "Lower sequencing coverage than the rest of the gene",
        "A small allele number means fewer individuals were confidently genotyped here, so the frequency estimate is "
        "less precise than for other variants in the gene.",
        "Prefer frequency estimates with larger allele numbers, or check coverage in the source browser."),
    "incomplete_clinvar_record": (
        "ClinVar record lacks allele-level coordinates",
        "Without exact chromosome, position and alleles the record cannot be matched to a population-frequency "
        "record. GeneLens never matches by gene name alone.",
        "Open the ClinVar record to see how the variant is described (e.g. a large deletion or protein-only notation)."),
    "ambiguous_match": (
        "Ambiguous database match",
        "More than one ClinVar record maps to this allele with different classifications, or the allele maps to "
        "several frequency records. Such matches are excluded from statistical tests by default.",
        "Inspect the linked ClinVar records and decide which interpretation applies to your question."),
    "frequency_outlier_within_class": (
        "Unusual frequency for its classification group",
        "Compared with other variants in the same classification group in this gene, this variant's frequency is "
        "far from the typical value (robust z-score). This is a statistical observation, not an interpretation.",
        "Look at the variant in context: its consequence, population distribution and review status."),
    "multivariate_outlier": (
        "Uncommon combination of features",
        "An Isolation Forest model found that this variant's combination of frequency, allele number, population "
        "skew, classification and review stars is rare within this gene.",
        "Use it as a pointer for manual inspection; the model gives no biological interpretation."),
}


def _fmt_pct(af):
    return "n/a" if af is None else (f"{af:.2e}" if af < 1e-4 else f"{af:.2%}")


def describe_flag(f: dict, row: dict) -> dict:
    """Return headline / reason / why_it_matters / recommendation for one flag."""
    headline, why, rec = CATEGORY_TEXT.get(f["category"], (f["category"].replace("_", " ").capitalize(), "", ""))
    ev = f.get("evidence") or {}
    sig = row.get("clinical_significance") or "unclassified"
    af = row.get("af")
    cat = f["category"]
    if cat == "frequent_pathogenic":
        th = ev.get("thresholds", {})
        crossed = []
        if af is not None and af >= th.get("af", 1):
            crossed.append(f"its overall allele frequency of {_fmt_pct(af)} exceeds the {th['af']:.2%} screening threshold")
        if (ev.get("popmax_af") or 0) >= th.get("popmax_af", 1):
            crossed.append(f"its frequency in the {ev.get('popmax_population')} group ({_fmt_pct(ev['popmax_af'])}) "
                           f"exceeds the {th['popmax_af']:.2%} population threshold")
        reason = (f"The variant is classified \"{sig}\" in ClinVar, but " + " and ".join(crossed or [
            f"its allele frequency is {_fmt_pct(af)}"]) + (f" (overall AF {_fmt_pct(af)})." if af is not None and
                                                           not (af >= th.get("af", 1)) else "."))
    elif cat == "ba1_frequency_non_benign":
        reason = f"Classified \"{sig}\" but observed at {_fmt_pct(max(af or 0, ev.get('popmax_af') or 0))}, above the 5% BA1 level."
    elif cat == "rare_benign":
        reason = f"Classified \"{sig}\" while observed at only {_fmt_pct(af)}."
    elif cat == "conflicting_interpretation":
        reason = "Different ClinVar submitters have provided conflicting interpretations for this variant."
    elif cat == "low_allele_number":
        reason = (f"Allele number {ev.get('an', 0):,} is {ev.get('fraction', 0):.0%} of the gene's median "
                  f"({ev.get('gene_median_an', 0):,.0f}).")
    elif cat == "frequency_outlier_within_class":
        reason = (f"Its frequency ({_fmt_pct(af)}) is {abs(ev.get('robust_z', 0)):.1f} robust standard deviations "
                  f"from the typical {str(ev.get('class', '')).replace('_', '/')} variant in this gene.")
    elif cat == "gnomad_qc_filter":
        reason = f"Quality filters reported: {', '.join(ev.get('filters') or []) or 'see source'}."
    else:
        reason = f.get("explanation", "")
    return {"headline": headline, "reason": reason, "why_it_matters": why, "recommendation": rec}


def enrich(flags: list[dict], rows: list[dict]) -> list[dict]:
    by_key = {r.get("vcf_key"): r for r in rows}
    for f in flags:
        f.update(describe_flag(f, by_key.get(f["variant_key"], {})))
    return flags
