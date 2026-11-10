"""Gene-constraint analysis (Module 5).

Constraint metrics describe how strongly a gene is depleted of a class of
variation in the general population compared with a mutational model.
They are *gene-level* population-genetics summaries and are **not**
predictions that any particular variant causes disease.
"""
from __future__ import annotations

METRIC_DOCS = {
    "pli": {
        "name": "pLI – probability of loss-of-function intolerance",
        "meaning": "Probability (0–1) that the gene falls in the class of genes intolerant of heterozygous "
                   "loss-of-function (LoF) variation. Values ≥ 0.9 are conventionally called LoF-intolerant.",
        "caveat": "pLI is dichotomising and sensitive to gene size; LOEUF is preferred for ranking.",
    },
    "oe_lof_upper": {
        "name": "LOEUF – LoF observed/expected upper bound fraction",
        "meaning": "Upper bound of the 90 % confidence interval of observed/expected LoF variants. Low values "
                   "mean strong depletion of LoF variants. gnomAD v4 suggests LOEUF < 0.6 as a constraint "
                   "threshold (v2 used < 0.35, its first decile).",
        "caveat": "Small genes have wide intervals, so a high LOEUF can reflect low power rather than tolerance.",
    },
    "oe_mis": {
        "name": "Missense observed/expected",
        "meaning": "Ratio of observed to expected missense variants. Values well below 1 suggest missense constraint.",
        "caveat": "Regional constraint can be masked by gene-wide averages.",
    },
    "mis_z": {
        "name": "Missense Z-score",
        "meaning": "Signed deviation of observed from expected missense counts; positive = fewer than expected.",
        "caveat": "Z ≥ 3.09 is a commonly used constraint cut-off.",
    },
    "oe_syn": {
        "name": "Synonymous observed/expected",
        "meaning": "Should be close to 1 because synonymous variants are mostly neutral – a calibration check.",
        "caveat": "Large deviations can indicate a problem with the mutational model for this gene.",
    },
}


def interpret_constraint(c: dict | None) -> dict:
    if not c:
        return {"available": False, "message": "No constraint metrics are available for this gene/dataset."}
    pli, loeuf, mis_z = c.get("pli"), c.get("oe_lof_upper"), c.get("mis_z")
    notes = []
    if pli is not None:
        notes.append(f"pLI = {pli:.3g}: " + ("in the LoF-intolerant class (≥ 0.9)." if pli >= 0.9 else
                                              "not in the LoF-intolerant class (< 0.9)."))
    if loeuf is not None:
        notes.append(f"LOEUF = {loeuf:.3f}: " + ("below 0.6 – strong depletion of LoF variants." if loeuf < 0.6
                                                 else "≥ 0.6 – no strong evidence of LoF depletion."))
    if mis_z is not None:
        notes.append(f"Missense Z = {mis_z:.2f}: " + ("≥ 3.09 – missense constrained." if mis_z >= 3.09
                                                      else "below the 3.09 constraint cut-off."))
    if c.get("oe_syn") is not None and not (0.8 <= c["oe_syn"] <= 1.2):
        notes.append(f"Synonymous o/e = {c['oe_syn']:.2f} deviates from 1; interpret other ratios cautiously.")
    rows = []
    for cls in ("lof", "mis", "syn"):
        if c.get(f"exp_{cls}") is not None:
            rows.append({"class": cls, "observed": c.get(f"obs_{cls}"), "expected": c.get(f"exp_{cls}"),
                         "oe": c.get(f"oe_{cls}"), "oe_lower": c.get(f"oe_{cls}_lower"),
                         "oe_upper": c.get(f"oe_{cls}_upper"), "z": c.get(f"{cls}_z")})
    return {
        "available": True, "metrics": c, "observed_expected": rows, "interpretation": notes,
        "flags": c.get("flags") or [], "docs": METRIC_DOCS,
        "disclaimer": "Constraint describes depletion of variation in a population sample. It does not predict "
                      "whether a specific variant or person will develop disease.",
    }
