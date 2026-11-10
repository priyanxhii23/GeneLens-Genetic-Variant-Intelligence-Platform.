"""Persist per-source health and usage (last success, last retrieval, record counts, errors).

Writes use their own short-lived session and never raise: a failure to record
statistics must not break a scientific retrieval.
"""
from __future__ import annotations

import logging

from app.models import SourceStatus, utcnow

log = logging.getLogger(__name__)


def _update(source_id: str, **fields):
    from app.database import SessionLocal

    try:
        with SessionLocal() as db:
            row = db.get(SourceStatus, source_id) or SourceStatus(source_id=source_id, records_retrieved=0)
            inc = fields.pop("_add_records", 0)
            for k, v in fields.items():
                setattr(row, k, v)
            row.records_retrieved = (row.records_retrieved or 0) + inc
            db.add(row)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        log.debug("could not record source status for %s: %s", source_id, exc)


def record_retrieval(source_id: str, n_records: int):
    now = utcnow()
    _update(source_id, last_retrieval_at=now, last_success_at=now, available=True, _add_records=int(n_records))


def record_error(source_id: str, error: str):
    _update(source_id, last_error=str(error)[:1000], last_error_at=utcnow())


def record_probe(source_id: str, available: bool, detail: str, release: str | None, latency_ms: int | None):
    fields = dict(available=available, detail=detail, latency_ms=latency_ms, last_checked_at=utcnow())
    if release:
        fields["release"] = release
    if available:
        fields["last_success_at"] = utcnow()
    else:
        fields.update(last_error=detail[:1000], last_error_at=utcnow())
    _update(source_id, **fields)
