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
from app.services.clinvar_client import ClinVarClient
from app.services.gnomad_client import DATASET_GENOME, GnomadClient, constraint_release
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
        genome = DATASET_GENOME[a.dataset]

        # 1. COLLECTION -------------------------------------------------------
        _progress(db, a, "Collecting gnomAD variants", 0.05)
        gene, gmeta = gnomad.fetch_gene_variants(a.gene_symbol, a.dataset)
        _progress(db, a, "Collecting ClinVar records", 0.25)
        if a.clinvar_source == "tsv":
            cv_raw, cmeta = clinvar.fetch_gene_tsv(a.gene_symbol, genome)
        else:
            if genome != "GRCh38":
                raise ValueError("E-utilities mode provides GRCh38 coordinates only. Use clinvar_source='tsv' "
                                 "for GRCh37 datasets (gnomAD v2.1 / ExAC).")
            cv_raw, cmeta = clinvar.fetch_gene_eutils(
                a.gene_symbol, progress=lambda f: _progress(db, a, "Collecting ClinVar records", 0.25 + 0.25 * f))
        for src, meta, n in (("gnomAD", gmeta, len(gene.get("variants") or [])), ("ClinVar", cmeta, len(cv_raw))):
            db.add(DatasetMetadata(analysis_id=a.id, source=src, dataset=meta.get("dataset"),
                                   release=meta.get("dataset_label") or meta.get("release"),
                                   reference_genome=genome, access_mode=meta.get("access_mode"),
                                   query=meta.get("query"), record_count=n,
                                   retrieved_at=_parse_dt(meta.get("retrieved_at"))))
        db.add(DatasetMetadata(analysis_id=a.id, source="gnomAD-constraint", dataset="gnomad_constraint",
                               release=constraint_release(genome), reference_genome=genome,
                               access_mode=gmeta.get("access_mode"),
                               query=f"gene({a.gene_symbol}).gnomad_constraint",
                               record_count=1 if gene.get("gnomad_constraint") else 0,
                               retrieved_at=_parse_dt(gmeta.get("retrieved_at")),
                               notes=f"canonical transcript {gene.get('canonical_transcript_id')}"))

        # 2. VALIDATION -------------------------------------------------------
        _progress(db, a, "Validating records", 0.55)
        errors = validate_gnomad_payload(gene)
        if errors:
            raise ValueError("gnomAD payload failed validation: " + "; ".join(errors))

        # 3–4. PREPROCESSING + NORMALISATION ------------------------------------
        _progress(db, a, "Preprocessing & normalising", 0.6)
        g_rows = preprocess_gnomad(gene)
        c_rows = preprocess_clinvar(cv_raw)

        # 5. MATCHING -------------------------------------------------------------
        _progress(db, a, "Matching gnomAD ↔ ClinVar", 0.65)
        rows, match_summary = match_variants(g_rows, c_rows, genome, genome)
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
        a.status, a.error, a.completed_at = "failed", f"{type(exc).__name__}: {exc}", utcnow()
        db.commit()
        log.error("Analysis %s failed: %s\n%s", analysis_id, exc, traceback.format_exc())
    return a


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
    return [variant_to_dict(v) for v in db.scalars(
        select(Variant).where(Variant.analysis_id == analysis_id, Variant.provenance == "REAL"))]


def load_rows(db: Session, analysis_id: str) -> list[dict]:
    return _load_rows(db, analysis_id)


def persist_anomalies(db: Session, analysis_id: str, rows: list[dict], thresholds: dict | None) -> dict:
    import uuid

    out = json_safe(anomaly_mod.detect_anomalies(rows, thresholds))
    run_id = uuid.uuid4().hex[:10]
    db.execute(delete(AnomalyResult).where(AnomalyResult.analysis_id == analysis_id))
    if out["flags"]:
        db.execute(insert(AnomalyResult), [{**{k: f[k] for k in ("variant_id", "variant_key", "provenance",
                   "category", "kind", "priority", "score", "evidence", "explanation")},
                   "analysis_id": analysis_id, "run_id": run_id} for f in out["flags"]])
    db.commit()
    out["run_id"] = run_id
    return out


def _qc_summary(rows: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in rows:
        for f in r.get("qc_flags") or []:
            counts[f] = counts.get(f, 0) + 1
    return {"flag_counts": counts, "records_with_flags": sum(1 for r in rows if r.get("qc_flags"))}
