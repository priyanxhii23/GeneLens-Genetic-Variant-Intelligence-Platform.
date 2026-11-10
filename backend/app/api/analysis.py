"""Analysis runs, results, statistics, populations, constraint and dashboard."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_analysis_or_404
from app.database import SessionLocal, get_db
from app.models import AnalysisSession, AnomalyResult, DatasetMetadata, SyntheticJob, Variant
from app.pipeline.constraint import interpret_constraint
from app.pipeline.populations import population_summary
from app.pipeline.runner import load_rows, load_synthetic_rows, run_analysis
from app.pipeline.statistics import run_statistics
from app.schemas import AnalysisRunRequest, AnalysisSummary, DatasetMetaOut
from app.datasets import BY_ID as DATASET_BY_ID
from app.services.gnomad_client import GnomadClient
from app.services.http import ExternalServiceError
from app.utils import user_message
from app.utils import json_safe

router = APIRouter(tags=["analysis"])


def _run_in_background(analysis_id: str):
    with SessionLocal() as db:
        run_analysis(db, analysis_id)


@router.post("/analysis/run", response_model=AnalysisSummary, status_code=status.HTTP_202_ACCEPTED)
def start_analysis(req: AnalysisRunRequest, bg: BackgroundTasks, db: Session = Depends(get_db)):
    spec = DATASET_BY_ID[req.dataset]
    genome = spec.assembly
    if req.clinvar_source not in spec.clinvar_sources:
        raise HTTPException(422, f"{spec.name} supports ClinVar sources {list(spec.clinvar_sources)} only.")
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


PROVENANCE = Query(None, pattern="^(REAL|SYNTHETIC|BOTH)$",
                   description="REAL, SYNTHETIC or BOTH. When given, the response is "
                               "{mode, groups: {REAL?: …, SYNTHETIC?: …}} – groups are always computed separately.")


def _rows_for(db: Session, analysis_id: str, provenance: str) -> dict:
    """Lazy row loaders per provenance group – rows are only read when a computation needs them."""
    groups = {}
    if provenance in ("REAL", "BOTH"):
        groups["REAL"] = lambda: load_rows(db, analysis_id)
    if provenance in ("SYNTHETIC", "BOTH"):
        groups["SYNTHETIC"] = lambda: load_synthetic_rows(db, analysis_id)
    return groups


def _has_synthetic(db: Session, analysis_id: str) -> bool:
    jobs = select(SyntheticJob.id).where(SyntheticJob.source_analysis_id == analysis_id)
    return bool(db.scalar(select(func.count()).select_from(Variant).where(Variant.synthetic_job_id.in_(jobs))))


@router.get("/analysis/statistics")
def statistics(analysis_id: str, include_ambiguous: bool | None = None, provenance: str | None = PROVENANCE,
               db: Session = Depends(get_db)):
    """Statistics for the selected provenance.

    Without ``provenance`` the stored REAL statistics are returned unchanged (original API shape).
    Real and synthetic records are never pooled: BOTH returns two separately computed groups.
    """
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    stored = (a.results or {}).get("statistics")
    seed = (a.parameters or {}).get("seed", 0)
    if provenance is None:
        if include_ambiguous is None or include_ambiguous == stored["sample"]["include_ambiguous"]:
            return stored
        return json_safe(run_statistics(load_rows(db, analysis_id), include_ambiguous=include_ambiguous, seed=seed))
    amb = stored["sample"]["include_ambiguous"] if include_ambiguous is None else include_ambiguous
    out = {}
    for name, loader in _rows_for(db, analysis_id, provenance).items():
        if name == "REAL" and amb == stored["sample"]["include_ambiguous"]:
            out[name] = stored  # pre-computed at analysis time – no rows needed
        elif name == "SYNTHETIC" and not _has_synthetic(db, analysis_id):
            out[name] = None
        else:
            rows = loader()
            out[name] = run_statistics(rows, include_ambiguous=amb, seed=seed) if rows else None
    return json_safe({"mode": provenance, "groups": out})


@router.get("/analysis/populations")
def populations(analysis_id: str, provenance: str | None = PROVENANCE, db: Session = Depends(get_db)):
    a = get_analysis_or_404(db, analysis_id, require_completed=True)
    stored = a.results.get("populations") or {}
    if "overview" not in stored:  # analyses stored before the overview existed: recompute once and keep it
        stored = json_safe(population_summary(load_rows(db, analysis_id)))
        a.results = {**a.results, "populations": stored}
        db.commit()
    if provenance is None:
        return stored
    out = {}
    for name, loader in _rows_for(db, analysis_id, provenance).items():
        if name == "REAL":
            out[name] = stored  # pre-computed – no rows needed
        elif not _has_synthetic(db, analysis_id):
            out[name] = None
        else:
            rows = loader()
            out[name] = population_summary(rows) if rows else None
    return json_safe({"mode": provenance, "groups": out})


@router.get("/analysis/pathogenicity")
def pathogenicity_extras(analysis_id: str, db: Session = Depends(get_db)):
    """VUS profile and classification by evaluation year (REAL data)."""
    from app.pipeline.pathogenicity import classification_by_year, vus_profile

    get_analysis_or_404(db, analysis_id, require_completed=True)
    rows = load_rows(db, analysis_id)
    return {"vus": vus_profile(rows), "history": classification_by_year(rows)}


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
            out.append({"symbol": s, "available": False, "error": user_message(exc)})
    return {"reference_genome": reference_genome, "genes": out,
            "docs": interpret_constraint({"pli": 0}).get("docs")}


@router.get("/dashboard")
def dashboard(analysis_id: str | None = None, provenance: str = Query("REAL", pattern="^(REAL|SYNTHETIC|BOTH)$"),
              db: Session = Depends(get_db)):
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
        syn_jobs = db.scalars(select(SyntheticJob.id).where(SyntheticJob.source_analysis_id == analysis_id)).all()
        scopes = {"REAL": (Variant.analysis_id == analysis_id) & (Variant.provenance == "REAL"),
                  "SYNTHETIC": Variant.synthetic_job_id.in_(syn_jobs) & (Variant.provenance == "SYNTHETIC")}
        wanted = ["REAL", "SYNTHETIC"] if provenance == "BOTH" else [provenance]
        groups = {}
        for name in wanted:
            cond = scopes[name]
            base = select(func.count()).select_from(Variant).where(cond)
            by_class = dict(db.execute(select(Variant.coarse_class, func.count()).where(
                cond, Variant.match_status != "secondary_clinvar").group_by(Variant.coarse_class)).all())
            by_match = dict(db.execute(select(Variant.match_status, func.count()).where(cond)
                                       .group_by(Variant.match_status)).all())
            flagged = db.scalar(select(func.count(func.distinct(AnomalyResult.variant_key))).where(
                AnomalyResult.analysis_id == analysis_id, AnomalyResult.provenance == name)) or 0
            groups[name] = {
                "total_records": db.scalar(base) or 0,
                "gnomad_variants": db.scalar(base.where(Variant.in_gnomad.is_(True))) or 0,
                "clinvar_records": db.scalar(base.where(Variant.in_clinvar.is_(True))) or 0,
                "matched": (sum(by_match.get(k, 0) for k in ("exact", "normalized", "synthetic")) +
                            (db.scalar(base.where(Variant.match_status == "ambiguous",
                                                  Variant.in_gnomad.is_(True))) or 0)),
                "pathogenic": by_class.get("P_LP", 0), "benign": by_class.get("B_LB", 0),
                "vus": by_class.get("VUS", 0), "conflicting": by_class.get("CONFLICTING", 0),
                "flagged": flagged, "by_match_status": by_match, "by_class": by_class,
            }
        syn_n = groups.get("SYNTHETIC", {}).get("total_records") if "SYNTHETIC" in groups else (
            db.scalar(select(func.count()).select_from(Variant).where(scopes["SYNTHETIC"])) or 0)
        out["analysis"] = AnalysisSummary.model_validate(a).model_dump()
        out["datasets"] = [DatasetMetaOut.model_validate(d).model_dump() for d in
                           db.scalars(select(DatasetMetadata).where(DatasetMetadata.analysis_id == analysis_id))]
        out["provenance"] = provenance
        out["groups"] = groups
        # "metrics" keeps the original shape: the selected group (REAL for BOTH; SYNTHETIC listed in groups)
        out["metrics"] = {**groups[wanted[0]], "real": a.real_count, "synthetic_linked": syn_n}
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
