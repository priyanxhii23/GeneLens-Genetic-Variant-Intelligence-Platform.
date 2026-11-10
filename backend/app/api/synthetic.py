"""Synthetic genome data lab endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import get_db
from app.models import AnalysisSession, DatasetMetadata, SyntheticJob, Variant
from app.pipeline import synthetic as syn
from app.pipeline.anomalies import detect_anomalies
from app.pipeline.runner import VARIANT_COLUMNS, load_rows
from app.schemas import SyntheticRequest
from app.utils import json_safe

router = APIRouter(tags=["synthetic"])


@router.post("/synthetic/generate", status_code=201)
def generate(req: SyntheticRequest, db: Session = Depends(get_db)):
    real_rows: list[dict] = []
    if req.source_analysis_id:
        a = get_analysis_or_404(db, req.source_analysis_id, require_completed=True)
        real_rows = load_rows(db, a.id)
    params = syn.SyntheticParams(**req.model_dump(exclude={"source_analysis_id"}))
    try:
        params.validate()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    model = json_safe(syn.fit_model(real_rows, seed=params.seed) if real_rows else dict(syn.DEFAULT_MODEL))
    job = SyntheticJob(source_analysis_id=req.source_analysis_id, n_records=params.n_records, seed=params.seed,
                       parameters=syn.params_to_dict(params), fitted_model=model, status="running")
    db.add(job)
    db.commit()
    records = syn.generate(params, model, job.id)
    payload = []
    for r in records:
        rec = {k: r.get(k) for k in VARIANT_COLUMNS if k in r}
        rec.update(synthetic_job_id=job.id, analysis_id=None, provenance="SYNTHETIC", variant_key=r["vcf_key"])
        payload.append(rec)
    for i in range(0, len(payload), 2000):
        db.execute(insert(Variant), payload[i:i + 2000])

    # Evaluate the anomaly engine against injected ground-truth scenarios.
    screen = detect_anomalies(records, {"use_isolation_forest": False})
    flagged = {f["variant_key"] for f in screen["flags"] if f["category"] in
               ("frequent_pathogenic", "rare_benign", "conflicting_interpretation")}
    injected_unusual = [r["vcf_key"] for r in records if "simulated_unusual_frequency" in r["qc_flags"]]
    injected_conflict = [r["vcf_key"] for r in records if "simulated_conflict" in r["qc_flags"]]
    evaluation = {
        "injected_unusual": len(injected_unusual),
        "injected_unusual_flagged": sum(1 for k in injected_unusual if k in flagged),
        "injected_conflicts": len(injected_conflict),
        "injected_conflicts_flagged": sum(1 for k in injected_conflict if k in flagged),
        "note": "Injected scenarios are known by construction, so this measures whether the rule engine "
                "recovers them under default thresholds (rare-benign injections below 1e-5 are expected to be "
                "caught; frequent-pathogenic injections ≥ 0.5 % likewise).",
    }
    comparison = syn.compare(real_rows, records) if real_rows else None
    if req.source_analysis_id:
        # Store screening flags for ALL synthetic rows of this analysis (provenance SYNTHETIC), with DB ids.
        db.flush()
        from app.pipeline.runner import load_synthetic_rows, persist_anomalies
        persist_anomalies(db, req.source_analysis_id, load_synthetic_rows(db, req.source_analysis_id),
                          None, provenance="SYNTHETIC")
    job.comparison = json_safe({"distribution": comparison, "anomaly_engine_evaluation": evaluation,
                      "screen_summary": screen["summary"]})
    job.status = "completed"
    db.add(DatasetMetadata(analysis_id=req.source_analysis_id, source="Synthetic", dataset=f"synthetic_job_{job.id}",
                           release=f"GeneLens synthetic generator (model: {model.get('source')})",
                           access_mode="generated", record_count=len(records),
                           query=f"seed={params.seed}; n={params.n_records}"))
    if req.source_analysis_id:
        a = db.get(AnalysisSession, req.source_analysis_id)
        a.synthetic_count = (a.synthetic_count or 0) + len(records)
    db.commit()
    return job_out(job, db)


def job_out(job: SyntheticJob, db: Session) -> dict:
    n = db.scalar(select(func.count()).select_from(Variant).where(Variant.synthetic_job_id == job.id))
    by_class = dict(db.execute(select(Variant.coarse_class, func.count()).where(Variant.synthetic_job_id == job.id)
                               .group_by(Variant.coarse_class)).all())
    return {"id": job.id, "provenance": "SYNTHETIC", "source_analysis_id": job.source_analysis_id,
            "n_records": job.n_records, "stored_records": n, "seed": job.seed, "parameters": job.parameters,
            "fitted_model": job.fitted_model, "comparison": job.comparison, "status": job.status,
            "created_at": job.created_at, "class_counts": by_class}


@router.get("/synthetic")
def list_jobs(source_analysis_id: str | None = None, db: Session = Depends(get_db)):
    q = select(SyntheticJob).order_by(SyntheticJob.created_at.desc())
    if source_analysis_id:
        q = q.where(SyntheticJob.source_analysis_id == source_analysis_id)
    return [{"id": j.id, "source_analysis_id": j.source_analysis_id, "n_records": j.n_records, "seed": j.seed,
             "status": j.status, "created_at": j.created_at, "model_source": (j.fitted_model or {}).get("source")}
            for j in db.scalars(q.limit(50))]


@router.get("/synthetic/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(SyntheticJob, job_id)
    if job is None:
        raise HTTPException(404, "Synthetic job not found")
    return job_out(job, db)
