"""Report generation and export history."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.config import get_settings
from app.database import get_db
from app.models import AnomalyResult, ExportRecord
from app.pipeline.reports import build_csv_report, build_pdf
from app.schemas import AnalysisSummary, DatasetMetaOut, ExportOut, ReportRequest

router = APIRouter(tags=["reports"])


@router.post("/reports/generate", response_model=ExportOut, status_code=201)
def generate_report(req: ReportRequest, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, req.analysis_id, require_completed=True)
    analysis = {**AnalysisSummary.model_validate(a).model_dump(), "results": a.results}
    datasets = [DatasetMetaOut.model_validate(d).model_dump() for d in a.datasets]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = f"GeneLens_{a.gene_symbol}_{a.id}_{stamp}.{req.format}"
    path = get_settings().reports_dir / fname
    if req.format == "pdf":
        flags = [{"variant_key": f.variant_key, "category": f.category, "kind": f.kind, "priority": f.priority,
                  "explanation": f.explanation} for f in db.scalars(
            select(AnomalyResult).where(AnomalyResult.analysis_id == a.id)
            .order_by(AnomalyResult.score.desc()).limit(200))]
        order = {"high": 0, "medium": 1, "low": 2}
        flags.sort(key=lambda f: order[f["priority"]])
        build_pdf(path, analysis, datasets, flags)
    else:
        build_csv_report(path, analysis, datasets)
    rec = ExportRecord(analysis_id=a.id, kind=f"{req.format}_report", filename=fname, path=str(path),
                       size_bytes=path.stat().st_size, parameters={"format": req.format})
    db.add(rec)
    db.commit()
    return rec


@router.get("/reports", response_model=list[ExportOut])
def list_reports(analysis_id: str | None = None, db: Session = Depends(get_db)):
    q = select(ExportRecord).order_by(ExportRecord.created_at.desc())
    if analysis_id:
        q = q.where(ExportRecord.analysis_id == analysis_id)
    return db.scalars(q.limit(200)).all()


@router.get("/reports/{export_id}/download")
def download(export_id: str, db: Session = Depends(get_db)):
    rec = db.get(ExportRecord, export_id)
    if rec is None:
        raise HTTPException(404, "Export not found")
    media = "application/pdf" if rec.filename.endswith(".pdf") else "text/csv"
    try:
        return FileResponse(rec.path, media_type=media, filename=rec.filename)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(410, "File no longer exists on disk") from exc
