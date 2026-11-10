"""Variant explorer: search, filter, sort, paginate, inspect, export."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AnomalyResult, ExportRecord, SyntheticJob, Variant
from app.pipeline.runner import variant_to_dict

router = APIRouter(tags=["variants"])

SORTABLE = {"pos", "af", "ac", "an", "popmax_af", "coarse_class", "gold_stars", "variant_key", "match_status"}
LIST_FIELDS = ["id", "variant_key", "provenance", "gene_symbol", "chrom", "pos", "ref", "alt", "variant_type",
               "rsid", "consequence", "hgvsc", "hgvsp", "name", "ac", "an", "af", "popmax_af", "popmax_population",
               "clinical_significance", "classification", "coarse_class", "review_status", "gold_stars",
               "match_status", "match_confidence", "in_gnomad", "in_clinvar", "qc_flags", "clinvar_variation_id"]
EXPORT_FIELDS = LIST_FIELDS + ["af_exome", "af_genome", "homozygote_count", "clinvar_allele_id", "conditions",
                               "submitter_count", "last_evaluated", "match_method", "gnomad_filters"]


def _filtered(analysis_id: str | None, synthetic_job_id: str | None, provenance: str, search: str | None,
              coarse_class: list[str] | None, match_status: list[str] | None, min_af: float | None,
              max_af: float | None, variant_type: str | None, flagged_only: bool, db: Session,
              top_population: str | None = None, custom_dataset_id: str | None = None) -> Select:
    if custom_dataset_id:  # custom datasets are only ever shown on their own
        q = select(Variant).where(Variant.custom_dataset_id == custom_dataset_id, Variant.provenance == "CUSTOM")
        return _apply_filters(q, search, coarse_class, match_status, min_af, max_af, variant_type, top_population)
    if not analysis_id and not synthetic_job_id:
        raise HTTPException(422, "Provide analysis_id, synthetic_job_id or custom_dataset_id")
    if provenance == "BOTH":  # UI name for ALL
        provenance = "ALL"
    q = select(Variant)
    scope = []
    if analysis_id and provenance in ("REAL", "ALL"):
        scope.append(Variant.analysis_id == analysis_id)
    if provenance in ("SYNTHETIC", "ALL"):
        if synthetic_job_id:
            scope.append(Variant.synthetic_job_id == synthetic_job_id)
        elif analysis_id:
            jobs = select(SyntheticJob.id).where(SyntheticJob.source_analysis_id == analysis_id)
            scope.append(Variant.synthetic_job_id.in_(jobs))
    if not scope:
        raise HTTPException(422, "No records match this provenance/scope combination")
    q = q.where(or_(*scope))
    q = _apply_filters(q, search, coarse_class, match_status, min_af, max_af, variant_type, top_population)
    if flagged_only and analysis_id:
        q = q.where(Variant.id.in_(select(AnomalyResult.variant_id).where(AnomalyResult.analysis_id == analysis_id)))
    return q


def _apply_filters(q, search, coarse_class, match_status, min_af, max_af, variant_type, top_population):
    if search:
        like = f"%{search.strip()}%"
        q = q.where(or_(Variant.variant_key.ilike(like), Variant.rsid.ilike(like), Variant.hgvsc.ilike(like),
                        Variant.hgvsp.ilike(like), Variant.name.ilike(like), Variant.conditions.ilike(like),
                        Variant.clinvar_variation_id == search.strip()))
    if coarse_class:
        q = q.where(Variant.coarse_class.in_(coarse_class))
    if match_status:
        q = q.where(Variant.match_status.in_(match_status))
    if min_af is not None:
        q = q.where(Variant.af >= min_af)
    if max_af is not None:
        q = q.where(Variant.af <= max_af)
    if variant_type:
        q = q.where(Variant.variant_type == variant_type)
    if top_population:
        q = q.where(Variant.popmax_population == top_population)
    return q


def _common(analysis_id: str | None = None, synthetic_job_id: str | None = None,
            provenance: str = Query("REAL", pattern="^(REAL|SYNTHETIC|ALL|BOTH)$"), search: str | None = None,
            coarse_class: list[str] | None = Query(None), match_status: list[str] | None = Query(None),
            min_af: float | None = Query(None, ge=0, le=1), max_af: float | None = Query(None, ge=0, le=1),
            variant_type: str | None = None, flagged_only: bool = False,
            top_population: str | None = Query(None, description="Population with the highest AF (grpmax group)"),
            custom_dataset_id: str | None = None):
    return dict(analysis_id=analysis_id, synthetic_job_id=synthetic_job_id, provenance=provenance, search=search,
                coarse_class=coarse_class, match_status=match_status, min_af=min_af, max_af=max_af,
                variant_type=variant_type, flagged_only=flagged_only, top_population=top_population,
                custom_dataset_id=custom_dataset_id)


@router.get("/variants")
def list_variants(f: dict = Depends(_common), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                  sort: str = "pos", order: str = Query("asc", pattern="^(asc|desc)$"), db: Session = Depends(get_db)):
    if sort not in SORTABLE:
        raise HTTPException(422, f"sort must be one of {sorted(SORTABLE)}")
    q = _filtered(db=db, **f)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    col = getattr(Variant, "variant_key" if sort == "variant_key" else sort)
    col = col.desc().nulls_last() if order == "desc" else col.asc().nulls_last()
    items = db.scalars(q.order_by(col, Variant.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size,
            "items": [{k: getattr(v, k) for k in LIST_FIELDS} for v in items]}


@router.get("/variants/export")
def export_variants(f: dict = Depends(_common), db: Session = Depends(get_db)):
    q = _filtered(db=db, **f).order_by(Variant.provenance, Variant.pos)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    scope = f["analysis_id"] or f["synthetic_job_id"] or f["custom_dataset_id"]
    fname = f"genelens_variants_{scope}_{f['provenance'].lower()}_{stamp}.csv"
    path = get_settings().exports_dir / fname
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write("# GeneLens variant export. provenance column: REAL = public database record; "
                 "SYNTHETIC = simulated, not a real observation; CUSTOM = researcher-uploaded data. "
                 "Empty cells = not available in the source record (never zero). Research use only.\n")
        w = csv.writer(fh)
        w.writerow(EXPORT_FIELDS + ["populations"])
        for v in db.scalars(q).yield_per(2000):
            pops = ";".join(f"{p['id']}:{p['ac']}/{p['an']}" for p in (v.populations or []))
            w.writerow([_csv(getattr(v, k)) for k in EXPORT_FIELDS] + [pops])
    rec = ExportRecord(analysis_id=f["analysis_id"], synthetic_job_id=f["synthetic_job_id"],
                       kind="synthetic_csv" if f["provenance"] == "SYNTHETIC" else "variants_csv",
                       filename=fname, path=str(path), size_bytes=path.stat().st_size,
                       parameters={k: v for k, v in f.items() if v})
    db.add(rec)
    db.commit()
    return StreamingResponse(open(path, "rb"), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


def _csv(v):
    if isinstance(v, list):
        return "|".join(map(str, v))
    return "" if v is None else v


@router.get("/variants/{variant_id}")
def variant_detail(variant_id: int, db: Session = Depends(get_db)):
    v = db.get(Variant, variant_id)
    if v is None:
        raise HTTPException(404, "Variant not found")
    d = variant_to_dict(v)
    d["anomalies"] = [{"category": a.category, "kind": a.kind, "priority": a.priority,
                       "explanation": a.explanation, "headline": a.headline,
                       "reason": a.reason, "why_it_matters": a.why_it_matters, "recommendation": a.recommendation}
                      for a in db.scalars(select(AnomalyResult).where(AnomalyResult.variant_id == variant_id))]
    d["assembly"], d["frequency_source"] = _context(db, v)
    if v.provenance == "REAL" and v.chrom and v.pos and v.in_gnomad:
        d["links"] = {"gnomad": f"https://gnomad.broadinstitute.org/variant/{v.variant_key}?dataset=gnomad_r4"}
    if v.clinvar_variation_id:
        d.setdefault("links", {})["clinvar"] = f"https://www.ncbi.nlm.nih.gov/clinvar/variation/{v.clinvar_variation_id}/"
    return d


def _context(db: Session, v: Variant) -> tuple[str, str | None]:
    """Genome assembly and frequency source for a record (never guessed)."""
    from app.models import AnalysisSession, CustomDataset

    if v.provenance == "SYNTHETIC":
        return "not applicable (simulated record)", "GeneLens synthetic generator"
    if v.custom_dataset_id:
        c = db.get(CustomDataset, v.custom_dataset_id)
        return (c.assembly if c else "unknown"), "custom dataset"
    a = db.get(AnalysisSession, v.analysis_id) if v.analysis_id else None
    src = ((a.results or {}).get("dataset") or {}).get("frequency_source", "gnomAD") if a else None
    return (a.reference_genome if a else "unknown"), src


@router.get("/variants/{variant_id}/evidence", include_in_schema=True, tags=["developer"])
def variant_evidence(variant_id: int, db: Session = Depends(get_db)):
    """Developer diagnostics: raw screening evidence for a variant (not used by the UI)."""
    return [{"category": a.category, "score": a.score, "evidence": a.evidence}
            for a in db.scalars(select(AnomalyResult).where(AnomalyResult.variant_id == variant_id))]
