"""Population frequency analysis (Module 4).

Population labels are gnomAD's genetic-ancestry groups. Results describe
aggregate allele frequencies in those reference samples only; they must not
be used to infer an individual's ancestry or disease risk.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.pipeline.preprocessing import GRPMAX_EXCLUDED, POPULATION_LABELS


def population_summary(rows: list[dict], top_n: int = 40) -> dict:
    variants = [r for r in rows if r.get("in_gnomad") and r.get("populations")]
    pop_ids = sorted({p["id"] for r in variants for p in r["populations"]})
    agg = {pid: {"id": pid, "label": POPULATION_LABELS.get(pid, pid), "grpmax_eligible": pid not in GRPMAX_EXCLUDED,
                 "variants_observed": 0, "total_ac": 0, "an_values": [], "missing": 0,
                 "by_class": defaultdict(lambda: {"observed": 0, "total_ac": 0})} for pid in pop_ids}
    for r in variants:
        seen = {p["id"]: p for p in r["populations"]}
        for pid in pop_ids:
            p = seen.get(pid)
            if not p or (not p.get("an") and p.get("af") is None):
                agg[pid]["missing"] += 1
                continue
            a = agg[pid]
            if p.get("an"):
                a["an_values"].append(p["an"])
            # uploaded datasets may report a population AF without AC/AN; AC is then left out of totals
            observed = p["ac"] > 0 if p.get("ac") is not None else (p.get("af") or 0) > 0
            if observed:
                a["variants_observed"] += 1
                a["total_ac"] += p.get("ac") or 0
                bc = a["by_class"][r.get("coarse_class", "NOT_IN_CLINVAR")]
                bc["observed"] += 1
                bc["total_ac"] += p.get("ac") or 0
    groups = []
    for pid, a in agg.items():
        an = np.array(a.pop("an_values"))
        groups.append({**a, "by_class": dict(a["by_class"]), "median_an": float(np.median(an)) if an.size else None,
                       "mean_an": float(an.mean()) if an.size else None, "missing_fraction": a["missing"] / len(variants) if variants else None})

    # per-variant matrix for the most frequent annotated variants
    ranked = sorted((r for r in variants if r.get("af")), key=lambda r: r["af"], reverse=True)[:top_n]
    matrix = []
    for r in ranked:
        pops = {p["id"]: p for p in r["populations"]}
        matrix.append({
            "variant_key": r["vcf_key"], "id": r.get("id"), "hgvsp": r.get("hgvsp"), "hgvsc": r.get("hgvsc"),
            "coarse_class": r.get("coarse_class"), "clinical_significance": r.get("clinical_significance"),
            "af": r["af"], "provenance": r.get("provenance", "REAL"),
            "populations": {pid: {"af": pops[pid].get("af"), "ac": pops[pid].get("ac"), "an": pops[pid].get("an")}
                            if pid in pops and (pops[pid].get("an") or pops[pid].get("af") is not None) else None for pid in pop_ids},
        })
    # distribution of popmax population among P/LP variants
    popmax_counts: dict[str, int] = defaultdict(int)
    for r in variants:
        if r.get("coarse_class") == "P_LP" and r.get("popmax_population"):
            popmax_counts[r["popmax_population"]] += 1
    return {
        "populations": pop_ids, "groups": groups, "matrix": matrix, "n_variants": len(variants),
        "pathogenic_popmax_distribution": dict(popmax_counts),
        "notes": [
            "Population groups are gnomAD genetic-ancestry labels for reference samples.",
            "'Missing' means the population had no allele number reported for that site (not AF = 0).",
            "grpmax excludes bottlenecked/small groups (ami, asj, fin, mid, remaining), as in gnomAD.",
            "These aggregate frequencies cannot be used to infer an individual's ancestry or disease risk.",
        ],
    }
