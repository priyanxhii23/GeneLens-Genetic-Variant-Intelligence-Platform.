"""Pathogenicity Lab extras: VUS profile and classification by evaluation year.

ClinVar's esummary/variant_summary expose only the *most recent* evaluation date per record, not the full
submission history, so the "history" view groups records by the year of their latest evaluation and is
labelled that way. Nothing is inferred about reclassification."""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np

from app.pipeline.statistics import wilson_ci

CLASSES = ["P_LP", "VUS", "B_LB", "CONFLICTING"]


def _year(s: str | None) -> int | None:
    m = re.search(r"(19|20)\d{2}", s or "")
    return int(m.group(0)) if m else None


def vus_profile(rows: list[dict]) -> dict:
    clin = [r for r in rows if r.get("in_clinvar") and r.get("match_status") != "secondary_clinvar"]
    vus = [r for r in clin if r.get("coarse_class") == "VUS"]
    with_af = [r for r in vus if r.get("af") is not None]
    afs = np.array([r["af"] for r in with_af if r["af"] > 0])
    bands = {"absent / AF missing": len(vus) - len(with_af),
             "AF = 0": sum(1 for r in with_af if r["af"] == 0),
             "< 0.01%": int((afs < 1e-4).sum()), "0.01–0.1%": int(((afs >= 1e-4) & (afs < 1e-3)).sum()),
             "0.1–1%": int(((afs >= 1e-3) & (afs < 1e-2)).sum()), "≥ 1%": int((afs >= 1e-2).sum())}
    high_pop = [r for r in vus if (r.get("popmax_af") or 0) >= 0.01]
    stars = Counter(str(r["gold_stars"]) if r.get("gold_stars") is not None else "not given" for r in vus)
    types = Counter(r.get("variant_type") or "unknown" for r in vus)
    return {
        "n_clinvar": len(clin), "n_vus": len(vus),
        "vus_fraction": len(vus) / len(clin) if clin else None,
        "vus_fraction_ci95": wilson_ci(len(vus), len(clin)) if clin else None,
        "frequency_bands": bands, "review_stars": dict(stars), "variant_types": dict(types.most_common(8)),
        "vus_with_population_af_over_1pct": len(high_pop),
        "examples_high_population_af": [{"id": r.get("id"), "variant_key": r.get("vcf_key"), "hgvsp": r.get("hgvsp"),
                                         "af": r.get("af"), "popmax_af": r.get("popmax_af"),
                                         "popmax_population": r.get("popmax_population")}
                                        for r in sorted(high_pop, key=lambda r: -(r.get("popmax_af") or 0))[:10]],
        "note": "A VUS observed at ≥1% in a population is a candidate for re-review with frequency evidence; frequency "
                "alone does not establish that it is benign.",
    }


def classification_by_year(rows: list[dict]) -> dict:
    clin = [r for r in rows if r.get("in_clinvar") and r.get("match_status") != "secondary_clinvar"]
    table: dict[int, Counter] = defaultdict(Counter)
    missing = 0
    for r in clin:
        y = _year(r.get("last_evaluated"))
        if y is None:
            missing += 1
            continue
        table[y][r.get("coarse_class") if r.get("coarse_class") in CLASSES else "OTHER"] += 1
    years = sorted(table)
    return {"years": years, "counts": {c: [table[y][c] for y in years] for c in CLASSES + ["OTHER"]},
            "without_date": missing, "available": bool(years),
            "label": "Year of most recent evaluation (ClinVar does not expose the full submission history via "
                     "these endpoints)."}
