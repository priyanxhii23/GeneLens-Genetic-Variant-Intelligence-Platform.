"""Analysis runs, results, statistics, populations, constraint and dashboard."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import SessionLocal, get_db
from app.models import AnalysisSession, AnomalyResult, DatasetMetadata, SyntheticJob, Variant
from app.pipeline.constraint import interpret_constraint
from app.pipeline.runner import load_rows, run_analysis
from app.pipeline.statistics import run_statistics
from app.schemas import AnalysisRunRequest, AnalysisSummary, DatasetMetaOut
from app.services.gnomad_client import DATASET_GENOME, GnomadClient
from app.services.http import ExternalServiceError
from app.utils import json_safe

router = APIRouter(tags=["analysis"])


def _run_in_background(analysis_id: str):
    with SessionLocal() as db:
        run_analysis(db, analysis_id)


@router.post("/analysis/run", response_model=AnalysisSummary, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(req: AnalysisRunRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    genome = DATASET_GENOME[req.dataset]
    if genome == "GRCh37" and req.clinvar_source == "eutils":
        raise HTTPException(422, "GRCh37 datasets require clinvar_source='tsv' (E-utilities SPDI is GRCh38-only).")
    a = AnalysisSession(gene_symbol=req.gene, dataset=req.dataset, reference_genome=genome,
                        clinvar_source=req.clinvar_source, status="queued", stage="Queued",
                        parameters={"include_ambiguous": req.include_ambiguous, "seed": req.seed,
                                    "anomaly_thresholds": req.anomaly_thresholds.model_dump()
                                    if req.anomaly_thresholds else None})
    db.add(a)
    db.commit()
    bg.add_task(_run_in_background, a.id)
    return a


@router.get("/analysis/{analysis_id}/status", response_model=AnalysisSummary)
def analysis_status(analysis_id: str, db: Session = Depends(get_db)):
    return get_analysis_or_404(db, analysis_id)


@router.get("/analysis/statistics")
def statistics(analysis_id: str, include_ambiguous: bool | None = None, db: Session = Depends(get_db)):
    """Stored statistics, or recomputed when ``include_ambiguous`` differs from the run's setting."""
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    stored = (a.results or {}).get("statistics")
    if include_ambiguous is None or include_ambiguous == stored["sample"]["include_ambiguous"]:
        return stored
    return json_safe(run_statistics(load_rows(db, analysis_id), include_ambiguous=include_ambiguous,
                                    seed=(a.parameters or {}).get("seed", 0)))


@router.get("/analysis/populations")
def populations(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    return a.results["populations"]


@router.get("/analysis/constraint")
def constraint(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    return {"gene": a.results["gene"], **a.results["constraint"]}


@router.get("/constraint/compare")
def constraint_compare(genes: str = Query(..., description="Comma-separated symbols, max 12"),
                       reference_genome: str = "GRCh38"):
    symbols = [g.strip().upper() for g in genes.split(",") if g.strip()][:12]
    client = GnomadClient()
    out = []
    for s in symbols:
        try:
            gene, meta = client.fetch_constraint(s, reference_genome)
            c = gene.get("gnomad_constraint")
            out.append({"symbol": gene["symbol"], "gene_id": gene["gene_id"],
                        "canonical_transcript_id": gene.get("canonical_transcript_id"), "available": bool(c),
                        "metrics": c, "access_mode": meta.get("access_mode"),
                        "retrieved_at": meta.get("retrieved_at")})
        except ExternalServiceError as exc:
            out.append({"symbol": s, "available": False, "error": str(exc)})
    return {"reference_genome": reference_genome, "genes": out,
            "docs": interpret_constraint({"pli": 0}).get("docs")}


@router.get("/dashboard")
def dashboard(analysis_id: str | None = None, db: Session = Depends(get_db)):
    """Command-center metrics, computed from stored rows (never hard-coded)."""
    recent = db.scalars(select(AnalysisSession).order_by(AnalysisSession.created_at.desc()).limit(8)).all()
    out: dict = {"recent": [AnalysisSummary.model_validate(r).model_dump() for r in recent]}
    total_real = db.scalar(select(func.count()).select_from(Variant).where(Variant.provenance == "REAL")) or 0
    total_syn = db.scalar(select(func.count()).select_from(Variant).where(Variant.provenance == "SYNTHETIC")) or 0
    out["database"] = {"real_records": total_real, "synthetic_records": total_syn,
                       "analyses": db.scalar(select(func.count()).select_from(AnalysisSession)),
                       "synthetic_jobs": db.scalar(select(func.count()).select_from(SyntheticJob))}
    if analysis_id:
        a = get_analysis_or_404(db, analysis_id)
        base = select(func.count()).select_from(Variant).where(Variant.analysis_id == analysis_id)
        by_class = dict(db.execute(select(Variant.coarse_class, func.count()).where(
            Variant.analysis_id == analysis_id, Variant.match_status != "secondary_clinvar")
            .group_by(Variant.coarse_class)).all())
        by_match = dict(db.execute(select(Variant.match_status, func.count()).where(
            Variant.analysis_id == analysis_id).group_by(Variant.match_status)).all())
        flagged = db.scalar(select(func.count(func.distinct(AnomalyResult.variant_key)))
                            .where(AnomalyResult.analysis_id == analysis_id)) or 0
        syn_jobs = db.scalars(select(SyntheticJob.id).where(SyntheticJob.source_analysis_id == analysis_id)).all()
        syn_n = db.scalar(select(func.count()).select_from(Variant).where(Variant.synthetic_job_id.in_(syn_jobs))) \
            if syn_jobs else 0
        out["analysis"] = AnalysisSummary.model_validate(a).model_dump()
        out["datasets"] = [DatasetMetaOut.model_validate(d).model_dump() for d in
                           db.scalars(select(DatasetMetadata).where(DatasetMetadata.analysis_id == analysis_id))]
        out["metrics"] = {
            "total_records": db.scalar(base) or 0,
            "gnomad_variants": db.scalar(base.where(Variant.in_gnomad.is_(True))) or 0,
            "clinvar_records": db.scalar(base.where(Variant.in_clinvar.is_(True))) or 0,
            "matched": sum(by_match.get(k, 0) for k in ("exact", "normalized")) +
            (db.scalar(base.where(Variant.match_status == "ambiguous", Variant.in_gnomad.is_(True))) or 0),
            "pathogenic": by_class.get("P_LP", 0), "benign": by_class.get("B_LB", 0),
            "vus": by_class.get("VUS", 0), "conflicting": by_class.get("CONFLICTING", 0),
            "flagged": flagged, "real": a.real_count, "synthetic_linked": syn_n,
            "by_match_status": by_match, "by_class": by_class,
        }
        if a.results:
            out["anomaly_summary"] = a.results.get("anomaly_summary")
            out["gene"] = a.results.get("gene")
            out["matching"] = a.results.get("matching")
    return out


# Declared last so static paths such as /analysis/statistics are matched first.
@router.get("/analysis/{analysis_id}")
def analysis_detail(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    return {"analysis": AnalysisSummary.model_validate(a).model_dump(),
            "datasets": [DatasetMetaOut.model_validate(d).model_dump() for d in a.datasets],
            "results": a.results}
