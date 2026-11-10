"""Research pipeline orchestrator.

COLLECTION → VALIDATION → PREPROCESSING → NORMALISATION → MATCHING →
STATISTICS → ANOMALY SCREENING → (VISUALISATION data) → INTERPRETATION

Each stage is a pure function in ``app.pipeline``; this module wires them
together, persists results and reports progress on the AnalysisSession row.
It can be run without the web server::

    python -m scripts.run_pipeline --gene HBB
"""
from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.models import AnalysisSession, AnomalyResult, DatasetMetadata, Gene, Variant, utcnow
from app.pipeline import anomalies as anomaly_mod
from app.pipeline.constraint import interpret_constraint
from app.pipeline.interpretation import interpret
from app.pipeline.matching import match_variants
from app.pipeline.populations import population_summary
from app.pipeline.preprocessing import preprocess_clinvar, preprocess_gnomad
from app.pipeline.statistics import run_statistics
from app.pipeline.validation import validate_gnomad_payload
from app.datasets import BY_ID as DATASET_BY_ID
from app.pipeline.preprocessing import preprocess_frequency_rows
from app.services.clinvar_client import ClinVarClient, to_grch37
from app.services.gnomad_client import GnomadClient, constraint_release
from app.services.http import ExternalServiceError
from app.utils import json_safe

log = logging.getLogger(__name__)

VARIANT_COLUMNS = {c.name for c in Variant.__table__.columns} - {"id"}


def _progress(db: Session, a: AnalysisSession, stage: str, progress: float):
    a.stage, a.progress = stage, round(progress, 3)
    db.commit()
    log.info("[%s] %s (%.0f%%)", a.id, stage, progress * 100)


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else utcnow()
    except ValueError:
        return utcnow()


def run_analysis(db: Session, analysis_id: str, gnomad: GnomadClient | None = None,
                 clinvar: ClinVarClient | None = None) -> AnalysisSession:
    a = db.get(AnalysisSession, analysis_id)
    if a is None:
        raise ValueError(f"analysis {analysis_id} not found")
    gnomad = gnomad or GnomadClient()
    clinvar = clinvar or ClinVarClient()
    params = a.parameters or {}
    t0 = time.time()
    try:
        a.status = "running"
        spec = DATASET_BY_ID.get(a.dataset)
        if spec is None:
            raise ValueError(f"Unknown dataset '{a.dataset}'")
        genome = spec.assembly

        # 1. COLLECTION – frequency / catalogue records (dataset-specific adapter) ---
        _progress(db, a, f"Collecting {spec.name}", 0.05)
        freq_rows, gene, fmeta, freq_label = _collect_frequency(spec, a.gene_symbol, gnomad,
                                                                 lambda f: _progress(db, a, f"Collecting {spec.name}", 0.05 + 0.15 * f))
        # ClinVar (always) – E-utilities or bulk TSV, expressed on the dataset's assembly
        _progress(db, a, "Collecting ClinVar records", 0.25)
        if a.clinvar_source == "tsv":
            cv_raw, cmeta = clinvar.fetch_gene_tsv(a.gene_symbol, genome)
        else:
            cv_raw, cmeta = clinvar.fetch_gene_eutils(
                a.gene_symbol, progress=lambda f: _progress(db, a, "Collecting ClinVar records", 0.25 + 0.25 * f))
            if genome == "GRCh37":
                cv_raw = [to_grch37(r) for r in cv_raw]
                cmeta = {**cmeta, "query": f"{cmeta.get('query')} (GRCh37 via ClinVar's own GRCh37 locations)"}
        sources = []
        if freq_label:
            sources.append((freq_label, fmeta, len(freq_rows)))
        sources.append(("ClinVar", cmeta, len(cv_raw)))
        for src, meta, n in sources:
            db.add(DatasetMetadata(analysis_id=a.id, source=src, dataset=meta.get("dataset"),
                                   release=meta.get("dataset_label") or meta.get("release"),
                                   reference_genome=genome, access_mode=meta.get("access_mode"),
                                   query=meta.get("query"), record_count=n,
                                   retrieved_at=_parse_dt(meta.get("retrieved_at")),
                                   notes="truncated to 25,000 RefSNPs" if meta.get("truncated") else None))
        if gene.get("gnomad_constraint") is not None or gene.get("_constraint_meta"):
            cm = gene.get("_constraint_meta") or fmeta
            db.add(DatasetMetadata(analysis_id=a.id, source="gnomAD-constraint", dataset="gnomad_constraint",
                                   release=constraint_release(genome), reference_genome=genome,
                                   access_mode=cm.get("access_mode"),
                                   query=f"gene({a.gene_symbol}).gnomad_constraint",
                                   record_count=1 if gene.get("gnomad_constraint") else 0,
                                   retrieved_at=_parse_dt(cm.get("retrieved_at")),
                                   notes=f"canonical transcript {gene.get('canonical_transcript_id')}"))

        # Gene annotation cross-check (Ensembl + UCSC); failures are recorded, never fatal
        _progress(db, a, "Annotating gene (Ensembl, UCSC)", 0.52)
        annotation = _annotate_gene(db, a, gene, genome)

        # 2. VALIDATION -------------------------------------------------------
        _progress(db, a, "Validating records", 0.55)
        if spec.kind == "gnomad":
            errors = validate_gnomad_payload(gene)
            if errors:
                raise ValueError("gnomAD payload failed validation: " + "; ".join(errors))

        # 3–4. PREPROCESSING + NORMALISATION ------------------------------------
        _progress(db, a, "Preprocessing & normalising", 0.6)
        g_rows = preprocess_gnomad(gene) if spec.kind == "gnomad" else preprocess_frequency_rows(freq_rows)
        c_rows = preprocess_clinvar(cv_raw)

        # 5. MATCHING -------------------------------------------------------------
        _progress(db, a, f"Matching {freq_label or 'records'} ↔ ClinVar", 0.65)
        rows, match_summary = match_variants(g_rows, c_rows, genome, genome)
        match_summary["frequency_source"] = freq_label
        if gene.get("symbol"):
            _upsert_gene(db, gene, genome)

        _progress(db, a, "Persisting variants", 0.7)
        db.execute(delete(Variant).where(Variant.analysis_id == a.id))
        payload = []
        for r in rows:
            rec = {k: r.get(k) for k in VARIANT_COLUMNS if k in r}
            rec.update(analysis_id=a.id, provenance="REAL", variant_key=r["vcf_key"],
                       rsid=r.get("rsid"), in_gnomad=bool(r.get("in_gnomad")),
                       in_clinvar=bool(r.get("in_clinvar")))
            payload.append(rec)
        for i in range(0, len(payload), 2000):
            db.execute(insert(Variant), payload[i:i + 2000])
        db.commit()
        from app.pipeline import rowcache
        rowcache.invalidate()
        stored = _load_rows(db, a.id)

        # 6. STATISTICS -------------------------------------------------------------
        _progress(db, a, "Running statistical tests", 0.8)
        stats = run_statistics(stored, include_ambiguous=params.get("include_ambiguous", False),
                               seed=params.get("seed", 0))

        # 7. ANOMALY SCREENING ---------------------------------------------------------
        _progress(db, a, "Screening for anomalies", 0.88)
        anomaly_out = persist_anomalies(db, a.id, stored, params.get("anomaly_thresholds"))

        # 8. VISUALISATION DATA + 9. INTERPRETATION -------------------------------------
        _progress(db, a, "Population & constraint analysis", 0.94)
        pops = population_summary(stored)
        constraint = interpret_constraint(gene.get("gnomad_constraint"))
        interp = interpret(a.gene_symbol, match_summary, stats, anomaly_out, constraint, pops)

        a.results = json_safe({
            "gene": {k: gene.get(k) for k in ("gene_id", "symbol", "name", "chrom", "start", "stop", "strand",
                                               "canonical_transcript_id")},
            "dataset": {"id": spec.id, "name": spec.name, "provider": spec.provider, "assembly": spec.assembly,
                        "data_type": spec.data_type, "frequency_source": freq_label},
            "gene_annotation": annotation,
            "matching": match_summary, "statistics": stats, "anomaly_summary": anomaly_out["summary"],
            "anomaly_thresholds": anomaly_out["thresholds"], "populations": pops, "constraint": constraint,
            "interpretation": interp, "qc": _qc_summary(stored),
            "runtime_seconds": round(time.time() - t0, 2),
        })
        a.real_count = len(stored)
        a.status, a.stage, a.progress, a.completed_at = "completed", "Completed", 1.0, utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - recorded on the session for the UI
        db.rollback()
        a = db.get(AnalysisSession, analysis_id)
        from app.utils import user_message
        a.status, a.error, a.completed_at = "failed", user_message(exc, log), utcnow()
        db.commit()
        log.error("Analysis %s failed: %s\n%s", analysis_id, exc, traceback.format_exc())
    return a


def _collect_frequency(spec, symbol: str, gnomad: GnomadClient, progress) -> tuple[list, dict, dict, str | None]:
    """Dispatch to the dataset's adapter. Returns (rows, gene, meta, frequency-source label)."""
    if spec.kind == "gnomad":
        gene, meta = gnomad.fetch_gene_variants(symbol, spec.id)
        return gene.get("variants") or [], gene, meta, "gnomAD"

    # Non-gnomAD datasets still use gnomAD for gene-level constraint (gene property, same assembly).
    gene: dict = {"symbol": symbol.upper()}
    try:
        g, cmeta = gnomad.fetch_constraint(symbol, spec.assembly)
        gene.update({k: g.get(k) for k in ("gene_id", "symbol", "name", "chrom", "start", "stop",
                                            "canonical_transcript_id", "mane_select_transcript", "gnomad_constraint")})
        gene["_constraint_meta"] = cmeta
    except ExternalServiceError as exc:
        log.warning("constraint unavailable for %s: %s", symbol, exc)

    if spec.kind == "igsr":
        from app.services.ensembl_client import EnsemblClient
        from app.services.igsr_client import IGSRClient

        loc = EnsemblClient().lookup_gene(symbol, "GRCh37")
        gene.update(symbol=loc["symbol"], gene_id=gene.get("gene_id") or loc["ensembl_id"],
                    name=gene.get("name") or loc["name"], chrom=loc["chrom"], start=loc["start"], stop=loc["end"])
        rows, meta = IGSRClient().fetch_region(loc["chrom"], loc["start"], loc["end"], loc["symbol"])
        return rows, gene, meta, "1000 Genomes"
    if spec.kind == "dbsnp":
        from app.services.dbsnp_client import DbSNPClient, snp_summary_to_rows

        docs, meta = DbSNPClient().fetch_gene(symbol, progress)
        rows = [r for d in docs for r in snp_summary_to_rows(d)]
        return rows, gene, meta, "dbSNP"
    if spec.kind == "clinvar_only":
        return [], gene, {}, None
    raise ValueError(f"No adapter for dataset kind '{spec.kind}'")


def _annotate_gene(db: Session, a: AnalysisSession, gene: dict, genome: str) -> dict:
    """Cross-check gene identity and coordinates across gnomAD, Ensembl and UCSC."""
    from app.services.ensembl_client import EnsemblClient
    from app.services.ucsc_client import UCSCClient

    out: dict = {"genome": genome, "sources": {}}
    if gene.get("start"):
        out["sources"]["gnomAD"] = {"chrom": gene.get("chrom"), "start": gene.get("start"), "end": gene.get("stop")}
    try:
        e = EnsemblClient().lookup_gene(a.gene_symbol, genome)
        out["sources"]["Ensembl"] = {"chrom": e["chrom"], "start": e["start"], "end": e["end"],
                                     "ensembl_id": e["ensembl_id"], "biotype": e["biotype"],
                                     "canonical_transcript": e["canonical_transcript"]}
        out["name"] = e.get("name")
        db.add(DatasetMetadata(analysis_id=a.id, source="Ensembl", dataset="ensembl_lookup",
                               release=EnsemblClient().release(), reference_genome=genome, access_mode="live_api",
                               query=f"lookup/symbol/homo_sapiens/{a.gene_symbol}", record_count=1))
        try:
            u = UCSCClient().gene_region(a.gene_symbol, genome, e["chrom"], e["start"], e["end"])
            out["sources"]["UCSC"] = {"chrom": e["chrom"], "start": u["start"], "end": u["end"],
                                      "transcripts": u["transcripts"]}
            out["cytoband"] = u.get("cytoband")
            db.add(DatasetMetadata(analysis_id=a.id, source="UCSC", dataset=u["track"], release=u["ucsc_db"],
                                   reference_genome=genome, access_mode="live_api",
                                   query=f"getData/track {u['track']} + cytoBand", record_count=len(u["transcripts"])))
        except ExternalServiceError as exc:
            out["ucsc_error"] = str(exc)
    except ExternalServiceError as exc:
        out["ensembl_error"] = str(exc)
    starts = [v["start"] for v in out["sources"].values() if v.get("start")]
    out["coordinates_agree_within_bp"] = (max(starts) - min(starts)) if len(starts) > 1 else None
    out["note"] = ("Gene boundaries differ slightly between sources because each uses a different transcript set "
                   "(gnomAD/Ensembl: gene span; UCSC: RefSeq Select transcript).")
    return out


def _upsert_gene(db: Session, gene: dict, genome: str):
    obj = db.scalar(select(Gene).where(Gene.symbol == gene["symbol"], Gene.reference_genome == genome))
    if obj is None:
        obj = Gene(symbol=gene["symbol"], reference_genome=genome)
        db.add(obj)
    mane = gene.get("mane_select_transcript") or {}
    obj.ensembl_id, obj.name, obj.chrom = gene.get("gene_id"), gene.get("name"), gene.get("chrom")
    obj.start, obj.stop = gene.get("start"), gene.get("stop")
    obj.canonical_transcript_id = gene.get("canonical_transcript_id")
    obj.mane_select_transcript = f"{mane.get('ensembl_id')}.{mane.get('ensembl_version')}" if mane else None
    obj.constraint = gene.get("gnomad_constraint")
    obj.constraint_source = constraint_release(genome)
    obj.retrieved_at = utcnow()


def variant_to_dict(v: Variant) -> dict:
    d = {c: getattr(v, c) for c in VARIANT_COLUMNS | {"id"}}
    d["vcf_key"] = v.variant_key
    return d


def _load_rows(db: Session, analysis_id: str) -> list[dict]:
    from app.pipeline import rowcache

    return rowcache.rows(db, ("REAL", analysis_id), Variant.analysis_id == analysis_id, Variant.provenance == "REAL")


def load_rows(db: Session, analysis_id: str) -> list[dict]:
    return _load_rows(db, analysis_id)


def persist_anomalies(db: Session, analysis_id: str, rows: list[dict], thresholds: dict | None,
                      provenance: str = "REAL") -> dict:
    """Screen ``rows`` and store their flags, replacing earlier flags of the same provenance."""
    import uuid

    out = json_safe(anomaly_mod.detect_anomalies(rows, thresholds))
    run_id = uuid.uuid4().hex[:10]
    db.execute(delete(AnomalyResult).where(AnomalyResult.analysis_id == analysis_id,
                                           AnomalyResult.provenance == provenance))
    if out["flags"]:
        db.execute(insert(AnomalyResult), [{**{k: f.get(k) for k in (
            "variant_id", "variant_key", "provenance", "category", "kind", "priority", "score", "evidence",
            "explanation", "headline", "reason", "why_it_matters", "recommendation")},
            "analysis_id": analysis_id, "run_id": run_id} for f in out["flags"]])
    db.commit()
    out["run_id"] = run_id
    return out


def load_synthetic_rows(db: Session, analysis_id: str) -> list[dict]:
    """SYNTHETIC rows from every synthetic job generated from this analysis."""
    from app.models import SyntheticJob
    from app.pipeline import rowcache

    jobs = select(SyntheticJob.id).where(SyntheticJob.source_analysis_id == analysis_id)
    return rowcache.rows(db, ("SYNTHETIC", analysis_id), Variant.synthetic_job_id.in_(jobs),
                         Variant.provenance == "SYNTHETIC")


def _qc_summary(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        for f in r.get("qc_flags") or []:
            counts[f] = counts.get(f, 0) + 1
    return {"flag_counts": counts, "records_with_flags": sum(1 for r in rows if r.get("qc_flags"))}
