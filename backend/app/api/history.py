"""Research history & provenance (Module 10)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import get_db
from app.models import AnalysisSession, ExportRecord, SyntheticJob
from app.schemas import AnalysisSummary, DatasetMetaOut, ExportOut

router = APIRouter(tags=["history"])


@router.get("/history")
def history(gene: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    q = select(AnalysisSession).order_by(AnalysisSession.created_at.desc()).limit(min(limit, 500))
    if gene:
        q = q.where(AnalysisSession.gene_symbol == gene.upper())
    out = []
    for a in db.scalars(q):
        d = AnalysisSummary.model_validate(a).model_dump()
        d["datasets"] = [DatasetMetaOut.model_validate(x).model_dump() for x in a.datasets]
        d["matched"] = ((a.results or {}).get("matching") or {}).get("matched_variants")
        d["flags"] = ((a.results or {}).get("anomaly_summary") or {}).get("total")
        out.append(d)
    return out


@router.get("/history/{analysis_id}")
def history_detail(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    return {
        "analysis": AnalysisSummary.model_validate(a).model_dump(),
        "datasets": [DatasetMetaOut.model_validate(d).model_dump() for d in a.datasets],
        "exports": [ExportOut.model_validate(e).model_dump() for e in db.scalars(
            select(ExportRecord).where(ExportRecord.analysis_id == a.id).order_by(ExportRecord.created_at.desc()))],
        "synthetic_jobs": [{"id": j.id, "n_records": j.n_records, "seed": j.seed, "created_at": j.created_at,
                            "parameters": j.parameters} for j in db.scalars(
            select(SyntheticJob).where(SyntheticJob.source_analysis_id == a.id))],
        "results": a.results,
    }


@router.delete("/history/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id)
    db.delete(a)
    db.commit()
    from app.pipeline import rowcache
    rowcache.invalidate()
