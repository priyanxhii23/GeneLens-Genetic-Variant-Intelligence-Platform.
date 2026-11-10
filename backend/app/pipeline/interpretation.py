"""Stage 9 – research interpretation.

Every sentence is generated from a computed value; when a test did not run,
the text says so. Nothing here asserts clinical conclusions.
"""
from __future__ import annotations

LIMITATIONS = [
    "ClinVar classifications are submitted assertions of varying review quality; they are not ground truth.",
    "Absence from gnomAD does not imply AF = 0 – the site may be uncovered or filtered.",
    "gnomAD is a reference sample, not a disease-free population; it under-represents many ancestries.",
    "Matching without the reference sequence relies on both sources being left-aligned; rare complex "
    "indels may remain unmatched.",
    "Haplotype and large structural ClinVar records cannot be matched at allele level and are reported separately.",
    "Statistical associations between frequency and classification partly reflect how classifications are made "
    "(frequency is itself ACMG/AMP evidence), so they are circular to some degree.",
    "Anomaly flags are prompts for expert review, not evidence of misclassification.",
    "This tool is for exploratory research and education only and must not be used for diagnosis or "
    "clinical decision-making.",
]


def _p(p):
    return "p < 1e-300" if p == 0 else (f"p = {p:.2e}" if p < 1e-3 else f"p = {p:.3f}")


def interpret(gene: str, matching: dict, statistics: dict, anomalies: dict, constraint: dict,
              populations: dict) -> dict:
    findings = []
    m = matching
    findings.append(
        f"{m['gnomad_records']:,} gnomAD variants and {m['clinvar_records']:,} ClinVar records were retrieved for "
        f"{gene}; {m['matched_variants']:,} alleles were matched "
        f"({(m['clinvar_match_rate'] or 0):.1%} of ClinVar records with allele-level coordinates).")
    for t in statistics.get("tests", []):
        if not t.get("ran"):
            findings.append(f"{t['test']} ({t.get('comparison') or t.get('variables')}) was not run: {t['reason']}")
            continue
        eff = t.get("effect_size") or {}
        eff_txt = ""
        if eff.get("value") is not None:
            eff_txt = f"; {eff['name']} = {eff['value']:.3g}"
            if eff.get("magnitude"):
                eff_txt += f" ({eff['magnitude']})"
        sig = "statistically significant" if t.get("significant_fdr_0.05") else "not statistically significant"
        findings.append(f"{t['test']} – {t.get('comparison') or t.get('variables')}: {_p(t['p_value'])}, "
                        f"BH-adjusted {_p(t['p_adjusted_bh'])}{eff_txt}; {sig} at FDR 5%.")
    desc = statistics.get("descriptive", {})
    if desc.get("P_LP", {}).get("n") and desc.get("B_LB", {}).get("n"):
        findings.append(f"Median AF: P/LP {desc['P_LP']['median']:.2e} (n={desc['P_LP']['n']}) vs B/LB "
                        f"{desc['B_LB']['median']:.2e} (n={desc['B_LB']['n']}).")
    s = anomalies.get("summary", {})
    if s:
        findings.append(f"Screening produced {s.get('total', 0)} flags across {s.get('flagged_variants', 0)} variants "
                        f"({s.get('by_kind', {}).get('biological_interest', 0)} biological-interest, "
                        f"{s.get('by_kind', {}).get('data_quality', 0)} data-quality, "
                        f"{s.get('by_kind', {}).get('statistical_outlier', 0)} statistical-outlier).")
        fp = s.get("by_category", {}).get("frequent_pathogenic", 0)
        if fp:
            findings.append(f"{fp} P/LP variant(s) exceed the configured frequency threshold; these warrant review "
                            "of inheritance mode, penetrance and population history rather than assumed error.")
    if constraint.get("available"):
        findings.extend(constraint.get("interpretation", []))
    ppd = populations.get("pathogenic_popmax_distribution") or {}
    if ppd:
        top = max(ppd.items(), key=lambda kv: kv[1])
        findings.append(f"Among P/LP variants observed in gnomAD, the population with the highest AF was most often "
                        f"'{top[0]}' ({top[1]} variants). This reflects sampling and population history and says "
                        "nothing about individual risk.")
    return {"findings": findings, "limitations": LIMITATIONS,
            "disclaimer": "GeneLens is an exploratory research tool. It is NOT a medical device and must not be "
                          "used for diagnosis, screening or clinical decision-making."}
