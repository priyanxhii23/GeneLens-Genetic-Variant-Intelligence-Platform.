"""Custom Dataset Lab API – upload, inspect, map, process, manage and export CUSTOM datasets."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import CustomDataset, Variant, utcnow
from app.pipeline import custom_dataset as cd
from app.pipeline import rowcache

router = APIRouter(prefix="/custom-datasets", tags=["custom datasets"])
MAX_BYTES = 200 * 1024 * 1024
CHUNK = 1024 * 1024
ASSEMBLIES = {"GRCh37", "GRCh38", "unknown"}


def _upload_dir(ds_id: str):
    d = get_settings().data_dir / "uploads" / ds_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _out(ds: CustomDataset, full: bool = True) -> dict:
    base = {k: getattr(ds, k) for k in ("id", "name", "filename", "file_format", "size_bytes", "assembly",
                                         "assembly_source", "status", "stage", "progress", "error",
                                         "created_at", "updated_at")}
    base["provenance"] = "CUSTOM"
    base["row_count"] = (ds.inspection or {}).get("row_count")
    base["has_cleaned"] = bool(ds.cleaned_path)
    if ds.summary:
        t = ds.summary.get("totals", {})
        base["totals"] = t
    if full:
        base.update(inspection=ds.inspection, mapping=ds.mapping, options=ds.options, summary=ds.summary,
                    history=ds.history or [])
    return base


def _get(db: Session, ds_id: str) -> CustomDataset:
    ds = db.get(CustomDataset, ds_id)
    if ds is None:
        raise HTTPException(404, "This custom dataset does not exist (it may have been deleted).")
    return ds


def _run(ds_id: str):
    with SessionLocal() as db:
        cd.process(db, ds_id)


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...), name: str | None = Form(None), db: Session = Depends(get_db)):
    """Stream the upload to disk in chunks, validate the format and return the inspection (with preview)."""
    filename = (file.filename or "dataset").replace("\\", "/").split("/")[-1][:200]
    ds = CustomDataset(name=(name or filename.rsplit(".", 1)[0])[:160], filename=filename, file_format="?",
                       stored_path="", status="inspecting")
    db.add(ds)
    db.flush()
    folder = _upload_dir(ds.id)
    target = folder / ("original" + (".vcf.gz" if filename.lower().endswith((".gz", ".bgz")) else
                                     "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""))
    sha, size, head = hashlib.sha256(), 0, b""
    try:
        with open(target, "wb") as fh:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise cd.DatasetError(f"The file is larger than the {MAX_BYTES // 1024 // 1024} MB upload limit.")
                if len(head) < 65536:
                    head += chunk[:65536 - len(head)]
                sha.update(chunk)
                fh.write(chunk)
        if size == 0:
            raise cd.DatasetError("The uploaded file is empty.")
        fmt = cd.detect_format(filename, head)
        inspection = cd.inspect(target, fmt)
    except cd.DatasetError as exc:
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        shutil.rmtree(folder, ignore_errors=True)
        from app.utils import user_message
        raise HTTPException(422, "The file could not be read: " + user_message(exc)) from exc
    asm = inspection["assembly"]
    ds.file_format, ds.size_bytes, ds.sha256, ds.stored_path = fmt, size, sha.hexdigest(), str(target)
    ds.assembly, ds.assembly_source = asm["value"], asm.get("source")
    ds.inspection, ds.mapping, ds.options = inspection, inspection["suggested_mapping"], {"clinvar": True}
    ds.status, ds.stage, ds.progress = "inspected", "Awaiting confirmation", 0.0
    cd._event(ds, "uploaded", f"{filename} · {size:,} bytes · {inspection['row_count']:,} records")
    db.commit()
    return _out(ds)


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    return [_out(d, full=False) for d in db.scalars(select(CustomDataset).order_by(CustomDataset.created_at.desc()))]


@router.get("/{ds_id}")
def get_dataset(ds_id: str, db: Session = Depends(get_db)):
    return _out(_get(db, ds_id))


class DatasetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    assembly: str | None = None
    mapping: dict[str, str | None] | None = None
    clinvar: bool | None = None


@router.patch("/{ds_id}")
def update_dataset(ds_id: str, body: DatasetUpdate, db: Session = Depends(get_db)):
    ds = _get(db, ds_id)
    if ds.status in ("queued", "processing"):
        raise HTTPException(409, "The dataset is being processed; wait for it to finish before editing.")
    changes = []
    if body.name is not None and body.name.strip() != ds.name:
        changes.append(f"renamed '{ds.name}' → '{body.name.strip()}'")
        ds.name = body.name.strip()
    if body.assembly is not None:
        if body.assembly not in ASSEMBLIES:
            raise HTTPException(422, "Assembly must be GRCh37, GRCh38 or unknown.")
        if body.assembly != ds.assembly:
            changes.append(f"assembly {ds.assembly} → {body.assembly}")
            ds.assembly, ds.assembly_source = body.assembly, ("user" if body.assembly != "unknown" else None)
    if body.mapping is not None:
        cols = set((ds.inspection or {}).get("columns") or [])
        bad = [v for v in body.mapping.values() if v and v not in cols]
        if bad:
            raise HTTPException(422, f"Unknown column(s): {', '.join(bad[:5])}.")
        unknown = [k for k in body.mapping if k not in cd.FIELDS]
        if unknown:
            raise HTTPException(422, f"Unknown field(s): {', '.join(unknown[:5])}.")
        used = [v for v in body.mapping.values() if v]
        if len(used) != len(set(used)):
            raise HTTPException(422, "Each column can be mapped to only one field.")
        ds.mapping = {f: body.mapping.get(f) for f in cd.FIELDS}
        changes.append("column mapping updated")
    if body.clinvar is not None:
        ds.options = {**(ds.options or {}), "clinvar": body.clinvar}
        changes.append(f"ClinVar matching {'on' if body.clinvar else 'off'}")
    if changes:
        ds.updated_at = utcnow()
        cd._event(ds, "edited", "; ".join(changes))
    db.commit()
    return _out(ds)


@router.post("/{ds_id}/process", status_code=202)
def process_dataset(ds_id: str, bg: BackgroundTasks, db: Session = Depends(get_db)):
    ds = _get(db, ds_id)
    if ds.status in ("queued", "processing"):
        raise HTTPException(409, "This dataset is already being processed.")
    action = "reprocess requested" if ds.summary or ds.status == "failed" else "analysis requested"
    ds.status, ds.stage, ds.progress, ds.error = "queued", "Queued", 0.0, None
    cd._event(ds, action, f"assembly {ds.assembly}")
    db.commit()
    bg.add_task(_run, ds.id)
    return _out(ds, full=False)


@router.delete("/{ds_id}", status_code=204)
def delete_dataset(ds_id: str, db: Session = Depends(get_db)):
    ds = _get(db, ds_id)
    db.execute(delete(Variant).where(Variant.custom_dataset_id == ds.id))
    db.delete(ds)
    db.commit()
    rowcache.invalidate()
    shutil.rmtree(get_settings().data_dir / "uploads" / ds_id, ignore_errors=True)
    return Response(status_code=204)


@router.get("/{ds_id}/cleaned.csv")
def download_cleaned(ds_id: str, db: Session = Depends(get_db)):
    ds = _get(db, ds_id)
    if not ds.cleaned_path:
        raise HTTPException(409, "Run the analysis first – the cleaned dataset is created during processing.")
    return FileResponse(ds.cleaned_path, media_type="text/csv",
                        filename=f"GeneLens_CUSTOM_{ds.name.replace(' ', '_')}_cleaned.csv")


@router.get("/{ds_id}/export")
def export_analysis(ds_id: str, format: str = "json", db: Session = Depends(get_db)):
    ds = _get(db, ds_id)
    if not ds.summary:
        raise HTTPException(409, "Run the analysis first – there are no results to export yet.")
    safe = ds.name.replace(" ", "_")
    meta = {"dataset": ds.name, "provenance": "CUSTOM", "source_file": ds.filename, "sha256": ds.sha256,
            "assembly": ds.assembly, "assembly_source": ds.assembly_source, "exported_at": utcnow().isoformat(),
            "notice": "CUSTOM DATA uploaded by the user – kept separate from official REAL datasets. "
                      "Research use only; not for clinical decisions."}
    if format == "json":
        body = json.dumps({"metadata": meta, "mapping": ds.mapping, "results": ds.summary}, indent=2, default=str)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="GeneLens_CUSTOM_{safe}_analysis.json"'})
    if format == "csv":
        s = ds.summary
        buf = io.StringIO()
        buf.write(f"# GeneLens analysis of CUSTOM dataset '{ds.name}' (assembly {ds.assembly}). Research use only.\n")
        w = csv.writer(buf)
        w.writerow(["section", "metric", "value"])
        for k, v in s.get("totals", {}).items():
            w.writerow(["totals", k, v])
        for k, v in s.get("field_status", {}).items():
            w.writerow(["field_status", k, v])
        for k, v in s.get("classification_distribution", {}).items():
            w.writerow(["classification", k, v])
        for k, v in s.get("missing_by_field", {}).items():
            w.writerow(["missing", k, v])
        for t in (s.get("statistics") or {}).get("tests", []):
            w.writerow(["test", " ".join(x for x in (t.get("test"), t.get("comparison")) if x), t.get("p_value") if t.get("ran") else f"not run: {t.get('reason', '')}"])
        for f in s.get("anomalies", []):
            w.writerow(["flag", f.get("variant_key"), f"{f.get('priority')}: {f.get('headline')}"])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="GeneLens_CUSTOM_{safe}_analysis.csv"'})
    raise HTTPException(422, "format must be json or csv")
