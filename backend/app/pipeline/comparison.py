"""Gene Comparison Lab: side-by-side gene metrics and what-if screening.

All numbers are computed from stored REAL records of each gene's most recent
completed analysis for the chosen dataset. Parameters (AF threshold, classes,
minimum review stars, populations) re-filter or re-compute those records; they
never alter the stored data. What-if analysis re-runs the frequency rules of
the anomaly engine with alternative thresholds: it shows how *screening
results* change, not how biology changes.
"""
from __future__ import annotations

import math

import numpy as np

from app.pipeline.anomalies import AnomalyThresholds, rule_based
from app.pipeline.preprocessing import GRPMAX_EXCLUDED
from app.pipeline.validation import compute_af

FREQ_CATEGORIES = ("frequent_pathogenic", "ba1_frequency_non_benign", "rare_benign")
CLASSES = ("P_LP", "VUS", "B_LB", "CONFLICTING")
HIST_EDGES = np.arange(-7, 0.5, 0.5)


def effective_rows(rows: list[dict], populations: list[str] | None, min_stars: int) -> list[dict]:
    """Copy rows with AF recomputed from the selected populations and ClinVar labels gated by review stars.

    * ``populations``: AF = ΣAC / ΣAN over the selected groups (None/empty = overall AF).
    * ``min_stars``: ClinVar classifications with fewer review stars are treated as unclassified.
    """
    out = []
    for r in rows:
        if r.get("match_status") == "secondary_clinvar":
            continue
        e = dict(r)
        if populations:
            sel = [p for p in r.get("populations") or [] if p["id"] in populations and p.get("an")]
            ac, an = sum(p["ac"] for p in sel), sum(p["an"] for p in sel)
            e["af"] = compute_af(ac, an) if sel else None
            e["an"] = an or None
            elig = [p for p in sel if p["id"] not in GRPMAX_EXCLUDED and p.get("ac")]
            top = max(elig, key=lambda p: p["ac"] / p["an"]) if elig else None
            e["popmax_af"] = top["ac"] / top["an"] if top else None
            e["popmax_population"] = top["id"] if top else None
        if e.get("in_clinvar") and (e.get("gold_stars") or 0) < min_stars:
            e["coarse_class"] = "BELOW_REVIEW_THRESHOLD"
        out.append(e)
    return out


def gene_metrics(rows: list[dict], results: dict, classes: list[str], af_threshold: float) -> dict:
    freq = [r for r in rows if r.get("in_gnomad")]
    matched = [r for r in rows if r.get("in_gnomad") and r.get("in_clinvar")
               and r.get("match_status") in ("exact", "normalized")]
    clin = [r for r in rows if r.get("in_clinvar")]
    counts = {c: sum(1 for r in clin if r.get("coarse_class") == c) for c in CLASSES}
    counts["BELOW_REVIEW_THRESHOLD"] = sum(1 for r in clin if r.get("coarse_class") == "BELOW_REVIEW_THRESHOLD")
    sel = [r for r in matched if r.get("coarse_class") in classes and (r.get("af") or 0) > 0]
    hist = {c: np.histogram(np.clip(np.log10([r["af"] for r in sel if r["coarse_class"] == c] or [np.nan]), -7, 0),
                            HIST_EDGES)[0].tolist() for c in classes}
    above = [r for r in sel if r["af"] >= af_threshold]
    afs = [r["af"] for r in sel]
    cons = (results.get("constraint") or {}).get("metrics") or {}
    return {
        "frequency_records": len(freq), "clinvar_records": len(clin), "matched": len(matched),
        "class_counts": counts, "selected_with_af": len(sel),
        "above_threshold": len(above),
        "above_threshold_by_class": {c: sum(1 for r in above if r["coarse_class"] == c) for c in classes},
        "median_af": float(np.median(afs)) if afs else None,
        "histogram": {"edges": HIST_EDGES.tolist(), "counts": hist},
        "pli": cons.get("pli"), "loeuf": cons.get("oe_lof_upper"), "mis_z": cons.get("mis_z"),
    }


def screen_counts(rows: list[dict], thresholds: dict) -> dict:
    t = AnomalyThresholds.from_dict({**thresholds, "use_isolation_forest": False})
    flags = [f for f in rule_based(rows, t) if f["category"] in FREQ_CATEGORIES]
    by_cat = {c: sum(1 for f in flags if f["category"] == c) for c in FREQ_CATEGORIES}
    return {"total": len(flags), "by_category": by_cat}


def whatif(rows: list[dict], baseline: dict, scenario: dict) -> dict:
    b, s = screen_counts(rows, baseline), screen_counts(rows, scenario)
    diff = s["total"] - b["total"]
    pct = (diff / b["total"] * 100) if b["total"] else (None if diff else 0.0)
    return {"baseline": b, "scenario": s, "difference": diff,
            "percent_change": None if pct is None or math.isinf(pct) else round(pct, 1),
            "by_category_difference": {c: s["by_category"][c] - b["by_category"][c] for c in FREQ_CATEGORIES}}


def explain_whatif(baseline: dict, scenario: dict, total_b: int, total_s: int) -> str:
    changes = []
    labels = {"pathogenic_af": "P/LP frequency threshold", "rare_benign_af": "rare-benign threshold",
              "ba1_af": "BA1 threshold", "pathogenic_popmax_af": "P/LP population threshold"}
    for k, lab in labels.items():
        if k in baseline and k in scenario and baseline[k] != scenario[k]:
            changes.append(f"{lab} from {baseline[k]:g} to {scenario[k]:g}")
    change_txt = "; ".join(changes) or "no threshold"
    direction = ("more" if total_s > total_b else "fewer" if total_s < total_b else "the same number of")
    return (f"Changing the {change_txt} produces {direction} frequency-related review flags "
            f"({total_b} → {total_s}). This reflects a change in screening parameters only – the underlying "
            "variants, frequencies and classifications are unchanged. Raising a pathogenic-frequency threshold "
            "flags fewer variants; lowering it flags more.")
