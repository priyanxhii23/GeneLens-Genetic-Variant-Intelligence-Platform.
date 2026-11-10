"""Anomaly screening endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import get_db
from app.models import AnomalyResult, Variant
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
                   priority: str | None = None,
                   provenance: str = Query("REAL", pattern="^(REAL|SYNTHETIC|BOTH)$"),
                   page: int = Query(1, ge=1),
                   page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    q = select(AnomalyResult).where(AnomalyResult.analysis_id == analysis_id)
    if kind:
        q = q.where(AnomalyResult.kind == kind)
    if category:
        q = q.where(AnomalyResult.category == category)
    if priority:
        q = q.where(AnomalyResult.priority == priority)
    if provenance != "BOTH":
        q = q.where(AnomalyResult.provenance == provenance)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    priority_rank = case({"high": 3, "medium": 2, "low": 1}, value=AnomalyResult.priority, else_=0)
    rows = db.scalars(q.order_by(priority_rank.desc(), AnomalyResult.score.desc(), AnomalyResult.id)
                      .offset((page - 1) * page_size).limit(page_size)).all()
    ids = [r.variant_id for r in rows if r.variant_id]
    variants = {v.id: v for v in db.scalars(select(Variant).where(Variant.id.in_(ids)))} if ids else {}
    return {"total": total, "page": page, "page_size": page_size,
            "summary": _summary(db, analysis_id, provenance), "thresholds": (a.results or {}).get("anomaly_thresholds"),
            "counts_by_provenance": dict(db.execute(select(AnomalyResult.provenance, func.count()).where(
                AnomalyResult.analysis_id == analysis_id).group_by(AnomalyResult.provenance)).all()),
            "items": [_item(r, variants.get(r.variant_id)) for r in rows]}


def _item(r: AnomalyResult, v: Variant | None) -> dict:
    return {"id": r.id, "variant_id": r.variant_id, "variant_key": r.variant_key, "provenance": r.provenance,
            "category": r.category, "kind": r.kind, "priority": r.priority, "score": r.score,  # no raw evidence
            "headline": r.headline, "reason": r.reason or r.explanation, "why_it_matters": r.why_it_matters,
            "recommendation": r.recommendation, "explanation": r.explanation,
            "clinical_significance": v.clinical_significance if v else None,
            "coarse_class": v.coarse_class if v else None, "af": v.af if v else None,
            "hgvsp": v.hgvsp if v else None, "hgvsc": v.hgvsc if v else None}


def _summary(db: Session, analysis_id: str, provenance: str) -> dict:
    """Flag counts for the selected provenance, computed from stored flags."""
    cond = [AnomalyResult.analysis_id == analysis_id]
    if provenance != "BOTH":
        cond.append(AnomalyResult.provenance == provenance)
    out = {"total": db.scalar(select(func.count()).select_from(AnomalyResult).where(*cond)) or 0,
           "flagged_variants": db.scalar(select(func.count(func.distinct(AnomalyResult.variant_key))).where(*cond)) or 0}
    for key, col in (("by_category", AnomalyResult.category), ("by_kind", AnomalyResult.kind),
                     ("by_priority", AnomalyResult.priority)):
        out[key] = dict(db.execute(select(col, func.count()).where(*cond).group_by(col)).all())
    return out
