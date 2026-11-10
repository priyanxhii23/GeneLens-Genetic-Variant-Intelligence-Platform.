"""Gene Comparison Lab endpoints (multi-gene comparison, what-if screening, saved comparisons)."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.datasets import BY_ID as DATASET_BY_ID
from app.models import AnalysisSession, DatasetMetadata, SavedComparison
from app.pipeline import comparison as cmp
from app.pipeline.runner import load_rows
from app.utils import json_safe

router = APIRouter(tags=["comparison"])


class CompareParams(BaseModel):
    genes: list[str] = Field(..., min_length=2, max_length=5)
    dataset: str = "gnomad_r4"
    af_threshold: float = Field(0.001, gt=0, le=1)
    classes: list[str] = Field(default_factory=lambda: ["P_LP", "VUS", "B_LB", "CONFLICTING"])
    min_stars: int = Field(0, ge=0, le=4)
    populations: list[str] = Field(default_factory=list)

    @field_validator("genes")
    @classmethod
    def _genes(cls, v):
        v = list(dict.fromkeys(g.strip().upper() for g in v if g.strip()))
        if not 2 <= len(v) <= 5:
            raise ValueError("select between 2 and 5 distinct genes")
        return v

    @field_validator("dataset")
    @classmethod
    def _ds(cls, v):
        if v not in DATASET_BY_ID:
            raise ValueError("unknown dataset")
        return v


class Thresholds(BaseModel):
    pathogenic_af: float = Field(0.005, gt=0, le=1)
    pathogenic_popmax_af: float = Field(0.01, gt=0, le=1)
    ba1_af: float = Field(0.05, gt=0, le=1)
    rare_benign_af: float = Field(1e-5, gt=0, le=1)


class WhatIfParams(CompareParams):
    baseline: Thresholds = Thresholds()
    scenario: Thresholds = Thresholds(pathogenic_af=0.001)


class SaveRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    params: CompareParams
    results: dict | None = None
    whatif: dict | None = None


def _latest(db: Session, gene: str, dataset: str) -> AnalysisSession | None:
    return db.scalar(select(AnalysisSession).where(
        AnalysisSession.gene_symbol == gene, AnalysisSession.dataset == dataset,
        AnalysisSession.status == "completed").order_by(AnalysisSession.completed_at.desc()).limit(1))


@router.post("/compare/run")
def compare_run(p: CompareParams, db: Session = Depends(get_db)):
    out = []
    for g in p.genes:
        a = _latest(db, g, p.dataset)
        if a is None:
            out.append({"gene": g, "status": "missing",
                        "message": f"No completed {DATASET_BY_ID[p.dataset].name} analysis for {g} yet."})
            continue
        rows = cmp.effective_rows(load_rows(db, a.id), p.populations, p.min_stars)
        # Real data sources only – the comparison never uses synthetic records.
        sources = sorted({d.source for d in db.scalars(select(DatasetMetadata).where(DatasetMetadata.analysis_id == a.id))
                          if d.source != "Synthetic"})
        out.append({"gene": g, "status": "ok", "analysis_id": a.id, "completed_at": a.completed_at,
                    "sources": sources, **cmp.gene_metrics(rows, a.results or {}, p.classes, p.af_threshold)})
    return json_safe({"params": p.model_dump(), "genes": out,
                      "note": "Computed from stored REAL records of each gene's latest completed analysis."})


@router.post("/compare/whatif")
def compare_whatif(p: WhatIfParams, db: Session = Depends(get_db)):
    per_gene, tb, ts = [], 0, 0
    for g in p.genes:
        a = _latest(db, g, p.dataset)
        if a is None:
            per_gene.append({"gene": g, "status": "missing"})
            continue
        rows = cmp.effective_rows(load_rows(db, a.id), p.populations, p.min_stars)
        w = cmp.whatif(rows, p.baseline.model_dump(), p.scenario.model_dump())
        tb += w["baseline"]["total"]
        ts += w["scenario"]["total"]
        per_gene.append({"gene": g, "status": "ok", **w})
    diff = ts - tb
    return json_safe({
        "baseline_thresholds": p.baseline.model_dump(), "scenario_thresholds": p.scenario.model_dump(),
        "genes": per_gene, "total": {"baseline": tb, "scenario": ts, "difference": diff,
                                     "percent_change": round(diff / tb * 100, 1) if tb else None},
        "explanation": cmp.explain_whatif(p.baseline.model_dump(), p.scenario.model_dump(), tb, ts)})


@router.post("/compare/saved", status_code=201)
def save(req: SaveRequest, db: Session = Depends(get_db)):
    s = SavedComparison(name=req.name, genes=req.params.genes, dataset=req.params.dataset,
                        parameters=req.params.model_dump(), results=json_safe({"run": req.results, "whatif": req.whatif}))
    db.add(s)
    db.commit()
    return _out(s)


@router.get("/compare/saved")
def list_saved(db: Session = Depends(get_db)):
    return [_out(s, brief=True) for s in db.scalars(select(SavedComparison).order_by(SavedComparison.created_at.desc()))]


@router.get("/compare/saved/{cid}")
def get_saved(cid: str, db: Session = Depends(get_db)):
    s = db.get(SavedComparison, cid)
    if s is None:
        raise HTTPException(404, "Saved comparison not found")
    return _out(s)


@router.delete("/compare/saved/{cid}", status_code=204)
def delete_saved(cid: str, db: Session = Depends(get_db)):
    s = db.get(SavedComparison, cid)
    if s is None:
        raise HTTPException(404, "Saved comparison not found")
    db.delete(s)
    db.commit()


@router.get("/compare/saved/{cid}/export")
def export_saved(cid: str, db: Session = Depends(get_db)):
    s = db.get(SavedComparison, cid)
    if s is None:
        raise HTTPException(404, "Saved comparison not found")
    buf = io.StringIO()
    buf.write(f"# GeneLens comparison '{s.name}' – dataset {s.dataset}; parameters {s.parameters}; REAL records only\n")
    w = csv.writer(buf)
    w.writerow(["gene", "analysis_id", "frequency_records", "clinvar_records", "matched", "P_LP", "VUS", "B_LB",
                "CONFLICTING", "below_review_threshold", "above_af_threshold", "median_af", "pLI", "LOEUF",
                "whatif_baseline_flags", "whatif_scenario_flags", "whatif_difference"])
    wi = {g["gene"]: g for g in ((s.results or {}).get("whatif") or {}).get("genes", [])}
    for g in ((s.results or {}).get("run") or {}).get("genes", []):
        if g.get("status") != "ok":
            w.writerow([g["gene"], "", "missing analysis"])
            continue
        c = g["class_counts"]
        x = wi.get(g["gene"], {})
        w.writerow([g["gene"], g["analysis_id"], g["frequency_records"], g["clinvar_records"], g["matched"],
                    c.get("P_LP"), c.get("VUS"), c.get("B_LB"), c.get("CONFLICTING"), c.get("BELOW_REVIEW_THRESHOLD"),
                    g["above_threshold"], g["median_af"], g["pli"], g["loeuf"],
                    (x.get("baseline") or {}).get("total"), (x.get("scenario") or {}).get("total"), x.get("difference")])
    fname = f"GeneLens_comparison_{s.id}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _out(s: SavedComparison, brief: bool = False) -> dict:
    d = {"id": s.id, "name": s.name, "genes": s.genes, "dataset": s.dataset, "parameters": s.parameters,
         "created_at": s.created_at}
    if not brief:
        d["results"] = s.results
    return d
