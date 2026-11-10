"""Health, data sources, dataset registry, gene search/suggestions and variant annotation."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.datasets import dataset_status
from app.models import AnalysisSession, SourceStatus, Variant
from app.services.http import ExternalServiceError
from app.utils import user_message
from app.sources.registry import BY_ID as SOURCE_BY_ID
from app.sources.registry import SOURCES

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    n = db.scalar(select(func.count()).select_from(AnalysisSession))
    return {"status": "ok", "app": get_settings().app_name, "database": "ok", "analyses": n}


def _source_row(src, db: Session, probe: dict | None = None) -> dict:
    st = db.get(SourceStatus, src.id)
    return {
        "id": src.id, "name": src.name, "provider": src.provider, "method": src.method, "endpoint": src.endpoint,
        "category": src.category, "provides": src.provides, "used_for": src.used_for, "homepage": src.homepage,
        "available": (probe or {}).get("available", st.available if st else None),
        "detail": (probe or {}).get("detail", st.detail if st else None),
        "release": (probe or {}).get("release") or (st.release if st else None),
        "latency_ms": (probe or {}).get("latency_ms", st.latency_ms if st else None),
        "last_checked_at": st.last_checked_at if st else None,
        "last_success_at": st.last_success_at if st else None,
        "last_retrieval_at": st.last_retrieval_at if st else None,
        "records_retrieved": st.records_retrieved if st else 0,
        "last_error": st.last_error if st else None, "last_error_at": st.last_error_at if st else None,
        **({"pipeline": clinvar_tsv_pipeline(probe, st)} if src.id == "clinvar_tsv" else {}),
    }


# ---- ClinVar bulk TSV: honest per-stage status + optional background download ------------------
_TSV_DOWNLOAD: dict = {"state": "idle", "bytes": 0, "total": None, "error": None, "started_at": None}


def clinvar_tsv_pipeline(probe: dict | None, st) -> dict:
    """Separate 'reachable', 'remote file available', 'downloaded', 'indexed' and 'records imported'."""
    from app.services.clinvar_client import ClinVarClient

    settings = get_settings()
    local = ClinVarClient().tsv_path
    extracts = sorted(settings.processed_dir.glob("clinvar_*_GRCh3*_*.csv.gz"))
    probe = probe or {}
    return {
        "source_reachable": probe.get("available"),
        "remote_file_available": probe.get("remote_file_available") if probe.get("available") else None,
        "remote_size_mb": probe.get("remote_size_mb"),
        "downloaded": local.exists(),
        "local_size_mb": round(local.stat().st_size / 1e6, 1) if local.exists() else None,
        "indexed_gene_extracts": len(extracts),
        "indexed_genes": sorted({p.name.split("_")[1] for p in extracts})[:50],
        "records_imported": (st.records_retrieved if st else 0) or 0,
        "download": dict(_TSV_DOWNLOAD),
    }


def _download_tsv_job():
    import time as _t

    from app.services.clinvar_client import ClinVarClient

    def prog(done: int, total: int):
        _TSV_DOWNLOAD.update(bytes=done, total=total)

    try:
        ClinVarClient().download_tsv(force=True, progress=None, byte_progress=prog)
        _TSV_DOWNLOAD.update(state="completed", finished_at=_t.time())
    except Exception as exc:  # noqa: BLE001
        _TSV_DOWNLOAD.update(state="failed", error=user_message(exc))


@router.post("/sources/clinvar_tsv/download", status_code=202)
def download_clinvar_tsv(bg: BackgroundTasks):
    """Start downloading variant_summary.txt.gz (~400 MB) in the background; progress is real byte counts."""
    import time as _t

    if _TSV_DOWNLOAD["state"] == "running":
        raise HTTPException(409, "The ClinVar TSV download is already running.")
    _TSV_DOWNLOAD.update(state="running", bytes=0, total=None, error=None, started_at=_t.time())
    bg.add_task(_download_tsv_job)
    return dict(_TSV_DOWNLOAD)


@router.get("/sources/clinvar_tsv/pipeline")
def clinvar_tsv_status(db: Session = Depends(get_db)):
    """Local-only view of the TSV stages (uses the cached probe; no new network request)."""
    from app.sources.status_cache import get_probes

    probes, _ = get_probes()
    return clinvar_tsv_pipeline(probes.get("clinvar_tsv"), db.get(SourceStatus, "clinvar_tsv"))


@router.get("/sources")
def list_sources(refresh: bool = False, db: Session = Depends(get_db)):
    """All registered connectors with live probe results and usage statistics.

    Probes run in parallel and are cached (stale-while-revalidate, 5 min); ``refresh=true`` forces a check.
    """
    from app.sources.status_cache import get_probes

    probes, _ = get_probes(force=refresh)
    db.expire_all()
    return [_source_row(s, db, probes.get(s.id)) for s in SOURCES]


@router.post("/sources/{source_id}/refresh")
def refresh_source(source_id: str, db: Session = Depends(get_db)):
    from app.sources.status_cache import update_one

    src = SOURCE_BY_ID.get(source_id)
    if src is None:
        raise HTTPException(404, f"Unknown source '{source_id}'")
    probe = src.check()
    update_one(source_id, probe)
    db.expire_all()
    return _source_row(src, db, probe)


@router.get("/sources/status")
def sources_status(refresh: bool = False, db: Session = Depends(get_db)):
    """Backward-compatible summary used by the landing page (gnomAD, ClinVar, ClinVar TSV)."""
    rows = {r["id"]: r for r in list_sources(refresh, db)}
    pick = lambda k: {"available": bool(rows[k]["available"]), "detail": rows[k]["detail"] or "",  # noqa: E731
                      "latency_ms": rows[k]["latency_ms"]}
    tsv = rows["clinvar_tsv"]
    return {"gnomad": pick("gnomad"), "clinvar": pick("clinvar_eutils"),
            "clinvar_tsv": {"available": "downloaded locally" in (tsv["detail"] or ""), "detail": tsv["detail"] or ""}}


@router.get("/datasets")
def datasets(refresh: bool = False):
    """The ten-dataset registry with live availability (cached 10 minutes)."""
    return dataset_status(refresh)


@router.get("/genes/search")
def gene_search(q: str = Query(..., min_length=1, max_length=32), reference_genome: str = "GRCh38"):
    from app.services.gnomad_client import GnomadClient

    try:
        hits = GnomadClient().search_genes(q, reference_genome)
        return {"query": q, "results": hits[:15], "source": "gnomAD gene_search"}
    except ExternalServiceError as exc:
        return {"query": q, "results": [], "source": "unavailable", "error": user_message(exc)}


@router.get("/genes/suggest")
def gene_suggest(q: str = "", limit: int = 12, live: bool = True, db: Session = Depends(get_db)):
    """Gene suggestions: curated starting genes + local catalogue + live gnomAD search.

    ``live=false`` answers from the local catalogue only (instant); the UI then
    requests ``live=true`` to append results from gnomAD's gene search.
    Each suggestion reports whether GeneLens already holds data for it (prior
    analyses / offline snapshot) and which datasets are compatible.
    """
    from app.genes import suggest

    analysed = {g: n for g, n in db.execute(
        select(AnalysisSession.gene_symbol, func.count()).where(AnalysisSession.status == "completed")
        .group_by(AnalysisSession.gene_symbol)).all()}
    return suggest(q, limit, analysed, live)


@router.get("/variants/{variant_id}/annotation")
def variant_annotation(variant_id: int, db: Session = Depends(get_db)):
    """On-demand Ensembl VEP annotation + NCBI Variation Services RefSNP record for one REAL variant."""
    from app.services.dbsnp_client import DbSNPClient
    from app.services.ensembl_client import EnsemblClient

    v = db.get(Variant, variant_id)
    if v is None:
        raise HTTPException(404, "Variant not found")
    if v.provenance != "REAL":
        raise HTTPException(422, "Synthetic records are simulated and have no external annotation.")
    a = db.get(AnalysisSession, v.analysis_id) if v.analysis_id else None
    genome = a.reference_genome if a else "GRCh38"
    out: dict = {"variant_key": v.variant_key, "genome": genome}
    if v.chrom and v.pos and v.ref is not None and v.alt is not None:
        try:
            out["vep"] = EnsemblClient().vep(v.chrom, v.pos, v.ref, v.alt, genome)
        except ExternalServiceError as exc:
            out["vep_error"] = user_message(exc)
    if v.rsid:
        try:
            out["dbsnp"] = DbSNPClient().refsnp(v.rsid)
        except ExternalServiceError as exc:
            out["dbsnp_error"] = user_message(exc)
    return out
