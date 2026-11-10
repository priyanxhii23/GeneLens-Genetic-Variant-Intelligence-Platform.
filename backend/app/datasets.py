"""Registry of the ten analysable datasets.

Each dataset declares its provider, assembly, data type and the connector
that serves it. ``dataset_status()`` checks availability with real requests:

* gnomAD datasets – the gnomAD ``DatasetId`` enum is introspected, so a dataset
  is only "available" if the live API still offers it;
* 1000 Genomes – IGSR API + phase 3 index file must answer;
* ClinVar Variant Summary – E-utilities (live) and/or the bulk TSV;
* dbSNP – E-utilities ``db=snp`` must answer.

Data types are kept distinct: *population_frequency* datasets provide AC/AN/AF;
the *clinical_annotation* dataset provides classifications only; the
*variant_catalogue* dataset provides RefSNP alleles with study frequencies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.gnomad_client import DATASET_GENOME


@dataclass(frozen=True)
class DatasetSpec:
    id: str
    name: str
    provider: str
    assembly: str
    release: str
    data_type: str          # population_frequency | clinical_annotation | variant_catalogue
    kind: str               # pipeline adapter: gnomad | igsr | clinvar_only | dbsnp
    source_ids: tuple[str, ...]
    description: str
    clinvar_sources: tuple[str, ...] = ("eutils", "tsv")


GNOMAD_NAMES = {
    "gnomad_r4": "gnomAD v4 – Exomes + Genomes", "gnomad_r4_non_ukb": "gnomAD v4 – Non-UKB Subset",
    "gnomad_r3": "gnomAD v3 – Genomes", "gnomad_r3_non_cancer": "gnomAD v3 – Non-Cancer",
    "gnomad_r2_1": "gnomAD v2.1 – Exomes + Genomes", "gnomad_r2_1_non_cancer": "gnomAD v2.1 – Non-Cancer",
    "exac": "ExAC",
}
GNOMAD_DESC = {
    "gnomad_r4": "gnomAD v4 combines exome and genome sequencing from hundreds of thousands of individuals "
                 "(joint exome+genome counts). The largest public allele-frequency resource.",
    "gnomad_r4_non_ukb": "gnomAD v4 with UK Biobank samples removed – useful when UK Biobank data must be "
                         "excluded or analysed separately.",
    "gnomad_r3": "gnomAD v3 whole genomes only (no exomes) – smaller but uniform coverage across genes, "
                 "including non-coding regions.",
    "gnomad_r3_non_cancer": "gnomAD v3 genomes excluding individuals from cancer-cohort studies – often used "
                            "for cancer-predisposition genes.",
    "gnomad_r2_1": "gnomAD v2.1 exomes + genomes on the older GRCh37 assembly; still widely cited.",
    "gnomad_r2_1_non_cancer": "gnomAD v2.1 excluding cancer-cohort samples (GRCh37).",
    "exac": "The Exome Aggregation Consortium (ExAC), gnomAD's predecessor: ~60,000 exomes on GRCh37.",
}

DATASETS: list[DatasetSpec] = [
    *[DatasetSpec(ds, GNOMAD_NAMES[ds],
                  "Broad Institute (gnomAD)", DATASET_GENOME[ds],
                  f"{ds} – latest release served by the gnomAD browser API", "population_frequency", "gnomad",
                  ("gnomad",), GNOMAD_DESC[ds],
                  ("eutils", "tsv") if DATASET_GENOME[ds] == "GRCh38" else ("eutils", "tsv"))
      for ds in ["gnomad_r4", "gnomad_r4_non_ukb", "gnomad_r3", "gnomad_r3_non_cancer", "gnomad_r2_1",
                 "gnomad_r2_1_non_cancer", "exac"]],
    DatasetSpec("igsr_1000g_phase3", "1000 Genomes Project – Phase 3", "IGSR / EMBL-EBI", "GRCh37",
                "Phase 3 (release 20130502)", "population_frequency", "igsr", ("igsr", "ensembl"),
                "2,504 individuals from 26 populations in 5 super-populations, whole-genome + exome sequencing. "
                "Records are read directly from the official tabix-indexed VCFs for the gene's GRCh37 region "
                "(region from Ensembl)."),
    DatasetSpec("clinvar_variant_summary", "ClinVar Variant Summary – NCBI", "NCBI", "GRCh38",
                "Weekly ClinVar release", "clinical_annotation", "clinvar_only", ("clinvar_eutils", "clinvar_tsv"),
                "Clinical classifications only – no population frequencies. Choose this to study classification, "
                "review-status and conflict patterns. Frequency-based statistics are reported as not applicable."),
    DatasetSpec("dbsnp_refsnp", "dbSNP RefSNP Dataset – NCBI", "NCBI", "GRCh38", "Current dbSNP build",
                "variant_catalogue", "dbsnp", ("dbsnp",),
                "Every RefSNP (rs) record annotated to the gene, with GRCh38 alleles and per-study frequencies "
                "(ALFA preferred, then gnomAD genomes / 1000 Genomes). Allele number is derived from the study's "
                "reported count ÷ frequency and flagged as derived. Capped at 25,000 RefSNPs per gene.",
                ("eutils",)),
]
BY_ID = {d.id: d for d in DATASETS}

def dataset_status(refresh: bool = False) -> list[dict]:
    """Registry entries with live availability, computed from the shared (parallel, cached) probes."""
    from app.sources.status_cache import get_probes

    checks, enum = get_probes(force=refresh)
    out = []
    for d in DATASETS:
        status, detail, release = "unavailable", "", d.release
        if d.kind == "gnomad":
            if d.id in enum:
                status, detail = "available", "Listed by the live gnomAD API (DatasetId enum)"
            else:
                detail = "gnomAD API unreachable" if not checks["gnomad"]["available"] else "Not offered by the gnomAD API"
        elif d.kind == "igsr":
            ok = checks["igsr"]["available"] and checks["ensembl"]["available"]
            status = "available" if ok else "unavailable"
            detail = ("IGSR data portal and phase 3 VCF index reachable; Ensembl GRCh37 for gene regions" if ok else
                      f"IGSR: {checks['igsr'].get('detail')} · Ensembl: {checks['ensembl'].get('detail')}")
        elif d.kind == "clinvar_only":
            live, tsv = checks["clinvar_eutils"], checks["clinvar_tsv"]
            if live["available"] or tsv.get("local_file"):
                status = "available"
                detail = ("Live via E-utilities" if live["available"] else "E-utilities unavailable") + "; bulk TSV " + (
                    "downloaded" if tsv.get("local_file") else "not downloaded (optional)")
            else:
                detail = live.get("detail", "")
            release = (tsv.get("release") or live.get("release") or d.release)
        elif d.kind == "dbsnp":
            status = "available" if checks["dbsnp"]["available"] else "unavailable"
            detail = checks["dbsnp"].get("detail", "")
            release = checks["dbsnp"].get("release") or d.release
        out.append({**asdict(d), "source_ids": list(d.source_ids), "clinvar_sources": list(d.clinvar_sources),
                    "status": status, "status_detail": detail, "release": release})
    return out
