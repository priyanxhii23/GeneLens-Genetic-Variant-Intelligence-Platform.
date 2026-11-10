"""Stage 5 – gnomAD ↔ ClinVar variant matching.

Rules (in priority order):

1. **exact** – identical ``chrom-pos-ref-alt`` VCF key (confidence 1.0).
2. **normalized** – identical minimal representation after allele trimming
   (handles anchor-base differences for indels; confidence 0.9).
3. **ambiguous** – a gnomAD variant receives several ClinVar records whose
   coarse classifications disagree, or a minimal key maps to several gnomAD
   records (confidence 0.5). Kept, flagged, and excluded from tests by default.
4. **clinvar_only** – ClinVar allele not present in the gnomAD dataset.
   Absence is *not* treated as AF = 0 (the site may be uncovered or filtered).
5. **unmatchable** – ClinVar record without allele-level coordinates
   (haplotypes, large CNVs, missing alleles). Never matched by position or gene.
6. **gnomad_only** – gnomAD variant with no ClinVar record.
7. **secondary_clinvar** – an additional ClinVar record for an allele that was
   already matched; kept visible but not double-counted.

Records are never joined merely because they share a gene symbol, and both
inputs must use the same reference genome.
"""
from __future__ import annotations

from collections import defaultdict

STATUS_CONFIDENCE = {"exact": 1.0, "normalized": 0.9, "ambiguous": 0.5}
MATCHED_STATUSES = {"exact", "normalized", "ambiguous"}

GNOMAD_FIELDS = [
    "gnomad_variant_id", "consequence", "hgvsc", "hgvsp", "ac", "an", "af", "af_exome", "af_genome",
    "homozygote_count", "popmax_af", "popmax_population", "populations", "gnomad_filters",
    "gnomad_flags", "count_basis",
]
CLINVAR_FIELDS = [
    "clinvar_variation_id", "clinvar_allele_id", "clinical_significance", "classification",
    "coarse_class", "review_status", "gold_stars", "conditions", "submitter_count",
    "last_evaluated", "clinvar_type", "name",
]


class AssemblyMismatchError(ValueError):
    pass


def _rank(c: dict) -> tuple:
    return (c.get("gold_stars") or 0, c.get("last_evaluated") or "", c.get("submitter_count") or 0)


def match_variants(gnomad: list[dict], clinvar: list[dict], gnomad_genome: str,
                   clinvar_genome: str) -> tuple[list[dict], dict]:
    if gnomad_genome != clinvar_genome:
        raise AssemblyMismatchError(
            f"gnomAD dataset is {gnomad_genome} but ClinVar records are {clinvar_genome}; "
            "variants on different assemblies cannot be matched by coordinates.")

    by_vcf: dict[str, int] = {}
    by_min: dict[str, list[int]] = defaultdict(list)
    for i, g in enumerate(gnomad):
        if g.get("coords_valid"):
            by_vcf[g["vcf_key"]] = i
            by_min[g["minimal_key"]].append(i)

    candidates: dict[int, list[tuple[str, dict]]] = defaultdict(list)
    rows: list[dict] = []
    for i, g in enumerate(gnomad):
        if not g.get("coords_valid"):  # e.g. IUPAC ambiguity codes (Y, R…) in dbSNP alleles
            g["vcf_key"] = f"{(g.get('source') or 'freq').lower()}:{g.get('rsid') or i}:{g.get('ref')}>{g.get('alt')}"
            g["qc_flags"] = sorted(set(g.get("qc_flags") or []) | {"invalid_allele_representation"})
    for c in clinvar:
        if not c.get("coords_valid"):
            rows.append(_clinvar_row(c, "unmatchable", "no_allele_level_coordinates"))
            continue
        if c["vcf_key"] in by_vcf:
            candidates[by_vcf[c["vcf_key"]]].append(("exact", c))
        elif c["minimal_key"] in by_min:
            hits = by_min[c["minimal_key"]]
            if len(hits) == 1:
                candidates[hits[0]].append(("normalized", c))
            else:
                row = _clinvar_row(c, "ambiguous", "minimal_key_multiple_gnomad_hits")
                row["qc_flags"] = sorted(set(row["qc_flags"]) | {"ambiguous_match"})
                rows.append(row)
        else:
            rows.append(_clinvar_row(c, "clinvar_only", "no_gnomad_record_at_allele"))

    for i, g in enumerate(gnomad):
        cands = candidates.get(i)
        if not cands:
            rows.append(_gnomad_row(g))
            continue
        cands.sort(key=lambda t: _rank(t[1]), reverse=True)
        method, primary = cands[0]
        classes = {c["coarse_class"] for _, c in cands}
        status = method
        method_desc = "vcf_key_exact" if method == "exact" else "minimal_representation"
        qc = set(g.get("qc_flags") or []) | set(primary.get("qc_flags") or [])
        if len(cands) > 1:
            qc.add("multiple_clinvar_records")
            if len(classes) > 1:
                status = "ambiguous"
                method_desc += "+discordant_clinvar_records"
                qc.add("ambiguous_match")
        row = {**_base(g), **{k: g.get(k) for k in GNOMAD_FIELDS}, **{k: primary.get(k) for k in CLINVAR_FIELDS}}
        row.update(in_gnomad=True, in_clinvar=True, match_status=status, match_method=method_desc,
                   match_confidence=STATUS_CONFIDENCE[status], qc_flags=sorted(qc),
                   rsid=g.get("rsid") or primary.get("rsid"),
                   other_clinvar_ids=[c["clinvar_variation_id"] for _, c in cands[1:]])
        rows.append(row)
        for _, extra in cands[1:]:
            r = _clinvar_row(extra, "secondary_clinvar", f"additional_record_for_{g['vcf_key']}")
            rows.append(r)

    return rows, summarize_matching(rows, gnomad, clinvar)


def _base(rec: dict) -> dict:
    return {k: rec.get(k) for k in ("gene_symbol", "chrom", "pos", "ref", "alt", "vcf_key",
                                    "minimal_key", "variant_type", "rsid")}


def _gnomad_row(g: dict) -> dict:
    row = {**_base(g), **{k: g.get(k) for k in GNOMAD_FIELDS}}
    row.update(in_gnomad=True, in_clinvar=False, coarse_class="NOT_IN_CLINVAR",
               match_status="gnomad_only", match_method="no_clinvar_record", match_confidence=None,
               qc_flags=list(g.get("qc_flags") or []))
    return row


def _clinvar_row(c: dict, status: str, method: str) -> dict:
    row = {**_base(c), **{k: c.get(k) for k in CLINVAR_FIELDS}}
    row.update(in_gnomad=False, in_clinvar=True, match_status=status, match_method=method,
               match_confidence=STATUS_CONFIDENCE.get(status), qc_flags=list(c.get("qc_flags") or []))
    if not row.get("vcf_key"):
        row["vcf_key"] = f"clinvar:{c.get('clinvar_variation_id')}"
    return row


def summarize_matching(rows: list[dict], gnomad: list[dict], clinvar: list[dict]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["match_status"]] += 1
    clinvar_with_coords = sum(1 for c in clinvar if c.get("coords_valid"))
    matched_clinvar = counts["exact"] + counts["normalized"] + sum(
        1 for r in rows if r["match_status"] == "ambiguous" and r.get("in_gnomad")) + counts["secondary_clinvar"]
    return {
        "gnomad_records": len(gnomad),
        "clinvar_records": len(clinvar),
        "clinvar_with_allele_coordinates": clinvar_with_coords,
        "status_counts": dict(counts),
        "matched_variants": counts["exact"] + counts["normalized"] + sum(
            1 for r in rows if r["match_status"] == "ambiguous" and r.get("in_gnomad")),
        "clinvar_match_rate": round(matched_clinvar / clinvar_with_coords, 4) if clinvar_with_coords else None,
        "gnomad_annotated_rate": round(
            sum(1 for r in rows if r.get("in_gnomad") and r.get("in_clinvar")) / len(gnomad), 4) if gnomad else None,
    }
