from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AnalysisSession


def get_analysis_or_404(db: Session, analysis_id: str, require_completed: bool = False) -> AnalysisSession:
    a = db.get(AnalysisSession, analysis_id)
    if a is None:
        raise HTTPException(404, f"Analysis '{analysis_id}' not found")
    if require_completed and a.status != "completed":
        raise HTTPException(409, f"Analysis '{analysis_id}' is {a.status}; results are not available yet")
    return a
