"""Health, data-source status, datasets and gene search."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AnalysisSession
from app.services.clinvar_client import ClinVarClient
from app.services.gnomad_client import DATASET_GENOME, DATASET_LABEL, GnomadClient
from app.services.http import ExternalServiceError

router = APIRouter(tags=["system"])
_status_cache: dict = {"at": 0.0, "value": None}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    n = db.scalar(select(func.count()).select_from(AnalysisSession))
    return {"status": "ok", "app": get_settings().app_name, "database": "ok", "analyses": n}


@router.get("/sources/status")
def sources_status(refresh: bool = False):
    """Ping gnomAD and NCBI. Cached for 2 minutes to respect rate limits."""
    if not refresh and _status_cache["value"] and time.time() - _status_cache["at"] < 120:
        return _status_cache["value"]
    out = {}
    t = time.time()
    try:
        meta = GnomadClient().ping()
        out["gnomad"] = {"available": True, "latency_ms": int((time.time() - t) * 1000),
                         "detail": f"gnomAD browser API reachable (its ClinVar mirror: {meta.get('clinvar_release_date')})"}
    except (ExternalServiceError, Exception) as exc:  # noqa: BLE001
        out["gnomad"] = {"available": False, "detail": str(exc)}
    t = time.time()
    try:
        ClinVarClient().ping()
        out["clinvar"] = {"available": True, "latency_ms": int((time.time() - t) * 1000),
                          "detail": "NCBI E-utilities reachable"}
    except (ExternalServiceError, Exception) as exc:  # noqa: BLE001
        out["clinvar"] = {"available": False, "detail": str(exc)}
    tsv = ClinVarClient().tsv_path
    out["clinvar_tsv"] = {"available": tsv.exists(), "path": str(tsv),
                          "detail": "Local variant_summary.txt.gz present" if tsv.exists()
                          else "Not downloaded (optional – run python -m scripts.download_clinvar)"}
    _status_cache.update(at=time.time(), value=out)
    return out


@router.get("/datasets")
def datasets():
    return [{"id": k, "label": DATASET_LABEL.get(k, k), "reference_genome": v,
             "clinvar_sources": ["eutils", "tsv"] if v == "GRCh38" else ["tsv"]}
            for k, v in DATASET_GENOME.items()]


@router.get("/genes/search")
def gene_search(q: str = Query(..., min_length=1, max_length=32), reference_genome: str = "GRCh38"):
    try:
        hits = GnomadClient().search_genes(q, reference_genome)
        return {"query": q, "results": hits[:15], "source": "gnomAD gene_search"}
    except ExternalServiceError as exc:
        return {"query": q, "results": [], "source": "unavailable", "error": str(exc)}
