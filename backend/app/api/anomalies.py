"""Anomaly screening endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import get_db
from app.models import AnomalyResult
from app.pipeline.runner import load_rows, persist_anomalies
from app.schemas import AnomalyDetectRequest

router = APIRouter(tags=["anomalies"])


@router.post("/anomalies/detect")
def detect(req: AnomalyDetectRequest, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, req.analysis_id, require_completed=True)
    out = persist_anomalies(db, a.id, load_rows(db, a.id), req.thresholds.model_dump())
    results = dict(a.results)
    results["anomaly_summary"], results["anomaly_thresholds"] = out["summary"], out["thresholds"]
    a.results = results
    db.commit()
    return {"run_id": out["run_id"], "thresholds": out["thresholds"], "summary": out["summary"]}


@router.get("/anomalies")
def list_anomalies(analysis_id: str, kind: str | None = None, category: str | None = None,
                   priority: str | None = None, page: int = Query(1, ge=1),
                   page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    q = select(AnomalyResult).where(AnomalyResult.analysis_id == analysis_id)
    if kind:
        q = q.where(AnomalyResult.kind == kind)
    if category:
        q = q.where(AnomalyResult.category == category)
    if priority:
        q = q.where(AnomalyResult.priority == priority)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    priority_rank = case({"high": 3, "medium": 2, "low": 1}, value=AnomalyResult.priority, else_=0)
    rows = db.scalars(q.order_by(priority_rank.desc(), AnomalyResult.score.desc(), AnomalyResult.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size,
            "summary": (a.results or {}).get("anomaly_summary"), "thresholds": (a.results or {}).get("anomaly_thresholds"),
            "items": [{"id": r.id, "variant_id": r.variant_id, "variant_key": r.variant_key,
                       "provenance": r.provenance, "category": r.category, "kind": r.kind,
                       "priority": r.priority, "score": r.score, "evidence": r.evidence,
                       "explanation": r.explanation} for r in rows]}
