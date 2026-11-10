"""Stage 3 – preprocessing / standardisation.

* Flattens nested gnomAD variant payloads into one standard row per variant.
* Normalises ClinVar clinical significance strings into controlled vocabulary.
* Derives ClinVar review "gold stars" from the review status text.
"""
from __future__ import annotations

from app.pipeline.normalization import normalize_record
from app.pipeline.validation import check_counts, compute_af, validate_clinvar_record

# ---------------------------------------------------------------------------
# Clinical classification normalisation
# ---------------------------------------------------------------------------
FINE_TO_COARSE = {
    "pathogenic": "P_LP",
    "likely_pathogenic": "P_LP",
    "pathogenic_likely_pathogenic": "P_LP",
    "uncertain_significance": "VUS",
    "likely_benign": "B_LB",
    "benign": "B_LB",
    "benign_likely_benign": "B_LB",
    "conflicting": "CONFLICTING",
    "other": "OTHER",
    "not_provided": "OTHER",
}
FINE_LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely pathogenic",
    "pathogenic_likely_pathogenic": "Pathogenic/Likely pathogenic",
    "uncertain_significance": "Uncertain significance",
    "likely_benign": "Likely benign",
    "benign": "Benign",
    "benign_likely_benign": "Benign/Likely benign",
    "conflicting": "Conflicting classifications",
    "other": "Other (risk factor, drug response, …)",
    "not_provided": "Not provided",
}
COARSE_LABELS = {
    "P_LP": "Pathogenic / Likely pathogenic",
    "VUS": "Uncertain significance",
    "B_LB": "Benign / Likely benign",
    "CONFLICTING": "Conflicting",
    "OTHER": "Other / not provided",
    "NOT_IN_CLINVAR": "Not in ClinVar",
}
_EXACT = {
    "pathogenic": "pathogenic",
    "pathogenic, low penetrance": "pathogenic",
    "likely pathogenic": "likely_pathogenic",
    "likely pathogenic, low penetrance": "likely_pathogenic",
    "pathogenic/likely pathogenic": "pathogenic_likely_pathogenic",
    "pathogenic/likely pathogenic/likely pathogenic, low penetrance": "pathogenic_likely_pathogenic",
    "pathogenic/likely pathogenic/pathogenic, low penetrance": "pathogenic_likely_pathogenic",
    "uncertain significance": "uncertain_significance",
    "likely benign": "likely_benign",
    "benign": "benign",
    "benign/likely benign": "benign_likely_benign",
    "not provided": "not_provided",
    "no classification for the single variant": "not_provided",
    "no classifications from unflagged records": "not_provided",
}


def normalize_classification(raw: str | None) -> tuple[str, str]:
    """Map a ClinVar significance string to (fine_class, coarse_class).

    ClinVar may append secondary terms after ';' or ',' (e.g. "Pathogenic;
    other" or "Benign; risk factor"). The germline classification is the first
    term; secondary terms are preserved in the raw string, not discarded.
    """
    if raw is None or str(raw).strip() == "":
        return "not_provided", "OTHER"
    text = str(raw).strip().lower()
    if text.startswith("conflicting"):
        return "conflicting", "CONFLICTING"
    if text in _EXACT:
        fine = _EXACT[text]
    else:
        primary = text.split(";")[0].strip()
        fine = _EXACT.get(primary)
        if fine is None:
            primary = primary.split(",")[0].strip()
            fine = _EXACT.get(primary, "other")
    return fine, FINE_TO_COARSE[fine]


def gold_stars(review_status: str | None) -> int | None:
    if not review_status:
        return None
    s = review_status.lower()
    if "practice guideline" in s:
        return 4
    if "expert panel" in s:
        return 3
    if "multiple submitters" in s and "no conflicts" in s:
        return 2
    if "conflicting" in s or "single submitter" in s:
        return 1
    return 0


# ---------------------------------------------------------------------------
# gnomAD flattening
# ---------------------------------------------------------------------------
# Groups excluded from "grpmax" because of bottleneck history or small size,
# mirroring gnomAD's own grpmax definition.
GRPMAX_EXCLUDED = {"ami", "asj", "fin", "mid", "remaining", "oth"}
POPULATION_LABELS = {
    "afr": "African / African American",
    "ami": "Amish",
    "amr": "Admixed American",
    "asj": "Ashkenazi Jewish",
    "eas": "East Asian",
    "fin": "Finnish",
    "mid": "Middle Eastern",
    "nfe": "Non-Finnish European",
    "sas": "South Asian",
    "remaining": "Remaining individuals",
    "oth": "Other",
}


def _is_ancestry_group(pid: str) -> bool:
    return "_" not in pid and pid.upper() not in {"XX", "XY"}


def _merge_populations(*blocks) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for block in blocks:
        if not block:
            continue
        for p in block.get("populations") or []:
            pid = p.get("id")
            if not pid or not _is_ancestry_group(pid):
                continue
            m = merged.setdefault(pid, {"id": pid, "ac": 0, "an": 0, "homozygote_count": 0})
            m["ac"] += p.get("ac") or 0
            m["an"] += p.get("an") or 0
            m["homozygote_count"] += p.get("homozygote_count") or 0
    return merged


def flatten_gnomad_variant(v: dict, gene_symbol: str) -> dict:
    exome, genome, joint = v.get("exome"), v.get("genome"), v.get("joint")
    qc: list[str] = []
    if joint and joint.get("an") is not None:
        ac, an = joint.get("ac"), joint.get("an")
        hom = joint.get("homozygote_count")
        pops = _merge_populations(joint)
        basis = "joint"
    else:
        blocks = [b for b in (exome, genome) if b]
        ac = sum(b.get("ac") or 0 for b in blocks) if blocks else None
        an = sum(b.get("an") or 0 for b in blocks) if blocks else None
        hom = sum(b.get("homozygote_count") or 0 for b in blocks) if blocks else None
        pops = _merge_populations(*blocks)
        basis = "+".join(n for n, b in (("exome", exome), ("genome", genome)) if b)
    qc += check_counts(ac, an)
    for name, b in (("exome", exome), ("genome", genome)):
        if b and b.get("af") is not None:
            qc += [f"{name}_{f}" for f in check_counts(b.get("ac"), b.get("an"), b.get("af")) if f.startswith("af_")]

    populations = []
    for pid, p in sorted(pops.items()):
        p_af = compute_af(p["ac"], p["an"])
        populations.append({**p, "af": p_af, "label": POPULATION_LABELS.get(pid, pid)})
    eligible = [p for p in populations if p["id"] not in GRPMAX_EXCLUDED and p["af"] is not None and p["ac"] > 0]
    top = max(eligible, key=lambda p: p["af"]) if eligible else None

    filters = sorted({f"{n}:{f}" for n, b in (("exome", exome), ("genome", genome), ("joint", joint))
                      if b for f in (b.get("filters") or [])})
    rec = {
        "source": "gnomAD",
        "gene_symbol": gene_symbol,
        "chrom": v.get("chrom"), "pos": v.get("pos"), "ref": v.get("ref"), "alt": v.get("alt"),
        "gnomad_variant_id": v.get("variant_id"),
        "rsid": (v.get("rsids") or [None])[0],
        "consequence": v.get("consequence"),
        "hgvsc": v.get("hgvsc"), "hgvsp": v.get("hgvsp"),
        "ac": ac, "an": an, "af": compute_af(ac, an),
        "af_exome": compute_af(exome.get("ac"), exome.get("an")) if exome else None,
        "af_genome": compute_af(genome.get("ac"), genome.get("an")) if genome else None,
        "homozygote_count": hom,
        "popmax_af": top["af"] if top else None,
        "popmax_population": top["id"] if top else None,
        "populations": populations,
        "gnomad_filters": filters,
        "gnomad_flags": list(v.get("flags") or []) + ([f"lof:{v['lof']}"] if v.get("lof") else []),
        "count_basis": basis,
        "qc_flags": sorted(set(qc)),
    }
    if any(f.endswith(":AC0") for f in filters) or (ac == 0):
        rec["qc_flags"].append("ac0_after_qc")
    if any(not f.endswith(":AC0") for f in filters):
        rec["qc_flags"].append("failed_gnomad_filter")
    return normalize_record(rec)


def preprocess_gnomad(gene: dict) -> list[dict]:
    symbol = gene.get("symbol")
    return [flatten_gnomad_variant(v, symbol) for v in gene.get("variants") or []]


FREQUENCY_NOT_REPORTED = {"no_population_frequency", "frequency_not_reported_for_allele"}


def preprocess_frequency_rows(rows: list[dict]) -> list[dict]:
    """Validate + normalise already-flattened rows from 1000 Genomes or dbSNP adapters."""
    out = []
    for r in rows:
        qc = list(r.get("qc_flags") or [])
        if not (FREQUENCY_NOT_REPORTED & set(qc)):  # absent frequency is not a data-quality defect
            qc += check_counts(r.get("ac"), r.get("an"))
            if r.get("an") and r.get("ac") is not None and r.get("af") is None:
                r = {**r, "af": compute_af(r["ac"], r["an"])}
        if r.get("gnomad_filters"):
            qc.append("failed_gnomad_filter")
        out.append(normalize_record({**r, "qc_flags": sorted(set(qc))}))
    return out


def preprocess_clinvar(records: list[dict]) -> list[dict]:
    out = []
    for r in records:
        fine, coarse = normalize_classification(r.get("clinical_significance"))
        rec = normalize_record({**r, "source": "ClinVar"})
        rec.update(
            classification=fine, coarse_class=coarse,
            gold_stars=gold_stars(r.get("review_status")),
            qc_flags=validate_clinvar_record(r),
        )
        if not rec["coords_valid"] and "missing_alleles" not in rec["qc_flags"] \
                and "multi_allele_record" not in rec["qc_flags"]:
            rec["qc_flags"].append("invalid_coordinates")
        out.append(rec)
    return out
